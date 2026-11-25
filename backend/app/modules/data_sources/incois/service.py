"""
INCOIS (Indian National Centre for Ocean Information Services) Data Provider.

Integrates INCOIS ERDDAP services (Ministry of Earth Sciences, Govt. of India)
for Indian Ocean satellite wind observations (ASCAT) and regional oceanographic
analyses (SST, Salinity).
"""

from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re
import time
from typing import Dict, List, Optional, Any
import urllib.parse
import uuid

import httpx
import numpy as np
import xarray as xr

from app.core.config import settings
from app.modules.data_sources.base import (
    BaseMarineProvider,
    ProviderMetadata,
    ProviderDatasetMeta,
    UnifiedRetrievalParams,
    UnifiedPreviewResult,
    UnifiedRetrievalResult,
    UnifiedValidationResult,
    UnifiedProvenanceInfo,
    VariableStatsSummary,
)
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
    InvalidBoundsError,
    RetrievalError,
)

logger = logging.getLogger(__name__)

INCOIS_BASE_URL = "https://erddap.incois.gov.in/erddap"

INCOIS_VERIFIED_DATASETS: Dict[str, ProviderDatasetMeta] = {
    "ascat_daily_datasets": ProviderDatasetMeta(
        provider_id="incois",
        dataset_id="ascat_daily_datasets",
        product_id="INCOIS_ASCAT_DAILY_WIND",
        product_title="INCOIS ASCAT Daily Surface Wind Speed and Stress Product",
        dataset_description=(
            "Daily gridded ocean surface wind speed, wind stress, and components derived "
            "from Advanced Scatterometer (ASCAT) on MetOp satellites over the Indian Ocean."
        ),
        available_variables=[
            "wind_speed",
            "wind_stress",
            "zonal_wind_stress",
            "meridional_wind_stress",
        ],
        variable_metadata={
            "wind_speed": {
                "standard_name": "wind_speed",
                "units": "m s-1",
                "long_name": "Ocean Surface Wind Speed",
                "valid_min": 0.0,
                "valid_max": 75.0,
            },
            "wind_stress": {
                "standard_name": "magnitude_of_surface_downward_stress",
                "units": "N m-2",
                "long_name": "Wind Stress Magnitude",
                "valid_min": 0.0,
                "valid_max": 5.0,
            },
            "zonal_wind_stress": {
                "standard_name": "surface_downward_eastward_stress",
                "units": "N m-2",
                "long_name": "Zonal (Eastward) Wind Stress",
                "valid_min": -5.0,
                "valid_max": 5.0,
            },
            "meridional_wind_stress": {
                "standard_name": "surface_downward_northward_stress",
                "units": "N m-2",
                "long_name": "Meridional (Northward) Wind Stress",
                "valid_min": -5.0,
                "valid_max": 5.0,
            },
        },
        temporal_resolution="daily",
        spatial_resolution="0.25 degree (~27 km)",
        data_type="satellite_observation",
        spatial_coverage={"min_lon": 30.0, "max_lon": 120.0, "min_lat": -40.0, "max_lat": 40.0},
        depth_levels_count=1,
        depth_min=10.0,
        depth_max=10.0,
        time_coverage_start="2010-01-01T00:00:00Z",
        source_documentation="https://erddap.incois.gov.in/erddap/info/ascat_daily_datasets/index.html",
        licence_information="MoES India Open Data Policy (Free for scientific & non-commercial use)",
        verification_status="verified",
    ),
    "incois_argo_sst_weekly": ProviderDatasetMeta(
        provider_id="incois",
        dataset_id="incois_argo_sst_weekly",
        product_id="INCOIS_ARGO_SST_WEEKLY",
        product_title="INCOIS Argo Weekly Indian Ocean Sea Surface Temperature Analysis",
        dataset_description="Weekly gridded sea surface temperature in the Indian Ocean derived from Argo floats.",
        available_variables=["sst"],
        variable_metadata={
            "sst": {
                "standard_name": "sea_surface_temperature",
                "units": "degree_C",
                "long_name": "Sea Surface Temperature",
                "valid_min": -2.0,
                "valid_max": 40.0,
            }
        },
        temporal_resolution="weekly",
        spatial_resolution="1.0 degree (~111 km)",
        data_type="in_situ_analysis",
        spatial_coverage={"min_lon": 30.0, "max_lon": 120.0, "min_lat": -40.0, "max_lat": 40.0},
        depth_min=0.0,
        depth_max=5.0,
        time_coverage_start="2002-01-01T00:00:00Z",
        source_documentation="https://incois.gov.in/OOS/ArgoData.jsp",
        licence_information="MoES India Open Data Policy",
        verification_status="verified",
    ),
    "incois_argo_salinity_weekly": ProviderDatasetMeta(
        provider_id="incois",
        dataset_id="incois_argo_salinity_weekly",
        product_id="INCOIS_ARGO_SALINITY_WEEKLY",
        product_title="INCOIS Argo Weekly Indian Ocean Surface Salinity Analysis",
        dataset_description="Weekly gridded sea surface salinity in the Indian Ocean derived from Argo floats.",
        available_variables=["salinity"],
        variable_metadata={
            "salinity": {
                "standard_name": "sea_surface_salinity",
                "units": "PSU",
                "long_name": "Sea Surface Salinity",
                "valid_min": 2.0,
                "valid_max": 42.0,
            }
        },
        temporal_resolution="weekly",
        spatial_resolution="1.0 degree (~111 km)",
        data_type="in_situ_analysis",
        spatial_coverage={"min_lon": 30.0, "max_lon": 120.0, "min_lat": -40.0, "max_lat": 40.0},
        depth_min=0.0,
        depth_max=5.0,
        time_coverage_start="2002-01-01T00:00:00Z",
        source_documentation="https://incois.gov.in/OOS/ArgoData.jsp",
        licence_information="MoES India Open Data Policy",
        verification_status="verified",
    ),
}


class INCOISMarineProvider(BaseMarineProvider):
    """
    INCOIS Data Provider connecting to INCOIS ERDDAP for Indian Ocean datasets.
    """

    def __init__(
        self,
        base_url: str = INCOIS_BASE_URL,
        timeout_seconds: float = 60.0,
        verify_ssl: Optional[bool] = None,
        ssl_ca_bundle: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

        # Production Default: SSL verification is strictly enabled (True)
        if ssl_ca_bundle:
            self.verify_ssl: Any = ssl_ca_bundle
        elif verify_ssl is not None:
            self.verify_ssl = verify_ssl
        elif hasattr(settings, "incois_ssl_ca_bundle") and settings.incois_ssl_ca_bundle:
            self.verify_ssl = settings.incois_ssl_ca_bundle
        elif hasattr(settings, "incois_verify_ssl"):
            self.verify_ssl = settings.incois_verify_ssl
        else:
            self.verify_ssl = True

        if self.verify_ssl is False:
            logger.warning(
                "SECURITY WARNING: INCOIS SSL certificate verification is explicitly disabled. "
                "This override is strictly restricted to local development environments lacking "
                "the Indian CCA/NIC root certificate and must NEVER be used in production."
            )

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id="incois",
            name="Indian National Centre for Ocean Information Services",
            organization="Ministry of Earth Sciences, Government of India (MoES)",
            base_url=self.base_url,
            documentation_url="https://incois.gov.in/",
            access_method="erddap_griddap",
            authentication_required=False,
            auth_description="Public open access for Indian Ocean operational oceanography and scientific research.",
            status="operational",
            supported_formats=["NetCDF-3", "NetCDF-4", "GeoTIFF", "CSV", "JSON"],
            rate_limits_info="Standard institutional fair use policy",
            licence_info="MoES India Open Access Policy: Free for academic, scientific, and disaster risk reduction use.",
        )

    def list_datasets(self) -> List[ProviderDatasetMeta]:
        return list(INCOIS_VERIFIED_DATASETS.values())

    def get_dataset(self, dataset_id: str) -> ProviderDatasetMeta:
        if dataset_id not in INCOIS_VERIFIED_DATASETS:
            raise DatasetNotFoundError(
                f"Dataset '{dataset_id}' not found in INCOIS catalogue. "
                f"Available datasets: {list(INCOIS_VERIFIED_DATASETS.keys())}"
            )
        return INCOIS_VERIFIED_DATASETS[dataset_id]

    def search_catalogue(
        self,
        query: str,
        variables: Optional[List[str]] = None,
        data_type: Optional[str] = None,
    ) -> List[ProviderDatasetMeta]:
        results = []
        q = query.lower()
        for meta in INCOIS_VERIFIED_DATASETS.values():
            text = f"{meta.dataset_id} {meta.product_title} {meta.dataset_description}".lower()
            if q in text:
                if variables and not any(v in meta.available_variables for v in variables):
                    continue
                if data_type and meta.data_type != data_type:
                    continue
                results.append(meta)
        return results

    def validate_parameters(self, params: UnifiedRetrievalParams) -> UnifiedRetrievalParams:
        meta = self.get_dataset(params.dataset_id)

        # Validate variables
        unknown_vars = [v for v in params.variables if v not in meta.available_variables]
        if unknown_vars:
            raise InvalidVariableError(
                f"Unknown variable(s) {unknown_vars} for INCOIS dataset '{params.dataset_id}'. "
                f"Available: {meta.available_variables}"
            )

        # Validate longitude bounds [-180, 360]
        if not (-180.0 <= params.minimum_longitude <= 360.0):
            raise InvalidBoundsError(f"minimum_longitude {params.minimum_longitude} out of range [-180, 360]")
        if not (-180.0 <= params.maximum_longitude <= 360.0):
            raise InvalidBoundsError(f"maximum_longitude {params.maximum_longitude} out of range [-180, 360]")
        if params.minimum_longitude > params.maximum_longitude:
            raise InvalidBoundsError(
                f"minimum_longitude ({params.minimum_longitude}) cannot exceed maximum_longitude ({params.maximum_longitude})"
            )

        # Validate latitude bounds [-90, 90]
        if not (-90.0 <= params.minimum_latitude <= 90.0):
            raise InvalidBoundsError(f"minimum_latitude {params.minimum_latitude} out of range [-90, 90]")
        if not (-90.0 <= params.maximum_latitude <= 90.0):
            raise InvalidBoundsError(f"maximum_latitude {params.maximum_latitude} out of range [-90, 90]")
        if params.minimum_latitude > params.maximum_latitude:
            raise InvalidBoundsError(
                f"minimum_latitude ({params.minimum_latitude}) cannot exceed maximum_latitude ({params.maximum_latitude})"
            )

        # Validate dates
        try:
            start_dt = datetime.fromisoformat(params.start_datetime.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(params.end_datetime.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidBoundsError(f"Invalid ISO datetime format: {exc}") from exc

        if start_dt > end_dt:
            raise InvalidBoundsError(
                f"start_datetime ({params.start_datetime}) must be before end_datetime ({params.end_datetime})"
            )

        return params

    def preview(self, params: UnifiedRetrievalParams) -> UnifiedPreviewResult:
        validated = self.validate_parameters(params)
        request_id = f"preview-{uuid.uuid4().hex[:12]}"

        start_dt = datetime.fromisoformat(validated.start_datetime.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(validated.end_datetime.replace("Z", "+00:00"))
        duration_days = max(1.0, (end_dt - start_dt).total_seconds() / 86400.0)

        d_lon = max(0.01, abs(validated.maximum_longitude - validated.minimum_longitude))
        d_lat = max(0.01, abs(validated.maximum_latitude - validated.minimum_latitude))
        bbox_area = round(d_lon * d_lat, 4)

        # Estimate grid points (0.25 degree resolution nominal)
        n_lon = max(1, int(d_lon / 0.25))
        n_lat = max(1, int(d_lat / 0.25))
        n_time = max(1, int(duration_days))
        estimated_points = n_lon * n_lat * n_time * len(validated.variables)
        estimated_size_mb = round(max(0.01, estimated_points * 4 / (1024 * 1024)), 3)

        return UnifiedPreviewResult(
            request_id=request_id,
            provider_id="incois",
            dataset_id=validated.dataset_id,
            estimated_size_mb=estimated_size_mb,
            estimated_total_points=estimated_points,
            bounding_box_area_deg2=bbox_area,
            duration_days=round(duration_days, 2),
            status="success",
            message=(
                f"Valid INCOIS parameters. Extent: {n_lon}x{n_lat} grid points over "
                f"{n_time} time steps ({bbox_area} deg²)."
            ),
            selected_extent={
                "min_lon": validated.minimum_longitude,
                "max_lon": validated.maximum_longitude,
                "min_lat": validated.minimum_latitude,
                "max_lat": validated.maximum_latitude,
                "start_time": validated.start_datetime,
                "end_time": validated.end_datetime,
            },
            variables=validated.variables,
        )

    def _build_griddap_url(self, params: UnifiedRetrievalParams) -> str:
        """
        Constructs the ERDDAP griddap query URL for INCOIS.
        IMPORTANT: INCOIS's Tomcat web server rejects unencoded brackets with HTTP 400.
        All brackets [ and ] must be encoded as %5B and %5D.
        """
        # Format timestamps for ERDDAP
        start_t = params.start_datetime if "T" in params.start_datetime else f"{params.start_datetime}T00:00:00Z"
        end_t = params.end_datetime if "T" in params.end_datetime else f"{params.end_datetime}T23:59:59Z"
        if not start_t.endswith("Z") and not "+" in start_t:
            start_t += "Z"
        if not end_t.endswith("Z") and not "+" in end_t:
            end_t += "Z"

        # Build query parts for each variable
        # For ascat_daily_datasets, the ERDDAP axes are (time, depth, latitude, longitude) where depth is 10.0m
        has_depth = (params.dataset_id == "ascat_daily_datasets")
        depth_clause = "[(10.0)]" if has_depth else ""

        var_queries = []
        for v in params.variables:
            part = (
                f"{v}"
                f"[({start_t}):1:({end_t})]"
                f"{depth_clause}"
                f"[({params.minimum_latitude}):1:({params.maximum_latitude})]"
                f"[({params.minimum_longitude}):1:({params.maximum_longitude})]"
            )
            var_queries.append(part)

        query_unencoded = ",".join(var_queries)
        # Encode brackets to satisfy Tomcat RFC 7230 parser
        query_encoded = (
            query_unencoded.replace("[", "%5B")
            .replace("]", "%5D")
            .replace("(", "%28")
            .replace(")", "%29")
            .replace('"', "%22")
        )

        url = f"{self.base_url}/griddap/{params.dataset_id}.nc?{query_encoded}"
        return url

    def retrieve(
        self,
        params: UnifiedRetrievalParams,
        job_id: Optional[str] = None,
        staging_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        **kwargs,
    ) -> UnifiedRetrievalResult:
        validated = self.validate_parameters(params)
        jid = job_id or f"incois-job-{uuid.uuid4().hex[:12]}"

        target_dir = staging_dir or output_dir or Path("dataset-staging/incois")
        job_dir = target_dir / jid if jid not in str(target_dir) else target_dir
        job_dir.mkdir(parents=True, exist_ok=True)

        filename = validated.output_filename or f"incois_{validated.dataset_id}_{jid[:8]}.nc"
        file_path = job_dir / filename

        query_url = self._build_griddap_url(validated)
        logger.info("Executing INCOIS ERDDAP query: %s", query_url)

        max_retries = 3
        backoff_seconds = 2.0
        response = None
        last_error = None

        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True, verify=self.verify_ssl) as client:
                for attempt in range(1, max_retries + 1):
                    try:
                        logger.info(f"[Job {jid}] INCOIS attempt {attempt}/{max_retries} requesting: {query_url}")
                        response = client.get(query_url)

                        if response.status_code == 200:
                            break
                        elif response.status_code == 404:
                            raise RetrievalError(
                                f"No data found matching criteria in INCOIS dataset '{validated.dataset_id}'. "
                                f"Extent: lat [{validated.minimum_latitude}, {validated.maximum_latitude}], "
                                f"lon [{validated.minimum_longitude}, {validated.maximum_longitude}], "
                                f"time [{validated.start_datetime}, {validated.end_datetime}]."
                            )
                        elif response.status_code in (502, 503, 504) and attempt < max_retries:
                            logger.warning(
                                f"[Job {jid}] INCOIS ERDDAP returned HTTP {response.status_code} (attempt {attempt}/{max_retries}). "
                                f"Retrying in {backoff_seconds}s..."
                            )
                            time.sleep(backoff_seconds)
                            backoff_seconds *= 2
                        else:
                            err_msg = response.text[:400]
                            raise RetrievalError(
                                f"INCOIS ERDDAP request failed with HTTP {response.status_code}: {err_msg}"
                            )
                    except (httpx.TransportError, httpx.TimeoutException) as exc:
                        last_error = exc
                        if attempt < max_retries:
                            logger.warning(
                                f"[Job {jid}] INCOIS network error: {exc}. Retrying in {backoff_seconds}s..."
                            )
                            time.sleep(backoff_seconds)
                            backoff_seconds *= 2
                        else:
                            raise RetrievalError(f"Network error querying INCOIS ERDDAP: {exc}") from exc

                if response is None or response.status_code != 200:
                    raise RetrievalError(
                        f"INCOIS ERDDAP request failed after {max_retries} attempts: "
                        f"{last_error or (response.text[:300] if response else 'No response')}"
                    )

                content = response.content
                file_path.write_bytes(content)

        except httpx.RequestError as exc:
            raise RetrievalError(f"Network error querying INCOIS ERDDAP: {exc}") from exc

        file_size = file_path.stat().st_size
        sha256_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

        return UnifiedRetrievalResult(
            job_id=jid,
            provider_id="incois",
            dataset_id=validated.dataset_id,
            file_path=file_path,
            file_format="NetCDF-3",
            file_size_bytes=file_size,
            sha256_checksum=sha256_hash,
            raw_metadata={
                "query_url": query_url,
                "retrieved_bytes": file_size,
                "provider": "INCOIS (MoES India)",
            },
        )

    def validate_data(
        self,
        file_path: Path,
        expected_params: Optional[UnifiedRetrievalParams] = None,
        params: Optional[UnifiedRetrievalParams] = None,
        **kwargs,
    ) -> UnifiedValidationResult:
        expected_params = expected_params or params
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = file_path.stat().st_size
        sha256_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        warnings: List[str] = []
        errors: List[str] = []

        try:
            ds = xr.open_dataset(file_path)
        except Exception as exc:
            return UnifiedValidationResult(
                file_path=str(file_path),
                provider_id="incois",
                dataset_id=expected_params.dataset_id if expected_params else "unknown",
                file_size_bytes=file_size,
                sha256_checksum=sha256_hash,
                is_valid=False,
                status="FAILED",
                spatial_bounds_valid=False,
                temporal_bounds_valid=False,
                coordinates_valid=False,
                variables_valid=False,
                errors=[f"Failed to parse NetCDF file: {exc}"],
            )

        with ds:
            has_lat = "latitude" in ds.coords or "latitude" in ds.variables
            has_lon = "longitude" in ds.coords or "longitude" in ds.variables
            has_time = "time" in ds.coords or "time" in ds.variables
            coords_valid = has_lat and has_lon and has_time

            spatial_valid = True
            temporal_valid = True

            min_lon = max_lon = min_lat = max_lat = None
            if has_lat:
                lats = ds["latitude"].values
                valid_lats = lats[~np.isnan(lats)]
                if len(valid_lats) > 0:
                    min_lat = float(np.min(valid_lats))
                    max_lat = float(np.max(valid_lats))
                    if min_lat < -90.0 or max_lat > 90.0:
                        spatial_valid = False
                        errors.append(f"Latitude out of bounds [-90, 90]: [{min_lat}, {max_lat}]")

            if has_lon:
                lons = ds["longitude"].values
                valid_lons = lons[~np.isnan(lons)]
                if len(valid_lons) > 0:
                    min_lon = float(np.min(valid_lons))
                    max_lon = float(np.max(valid_lons))
                    if min_lon < -180.0 or max_lon > 360.0:
                        spatial_valid = False
                        errors.append(f"Longitude out of bounds [-180, 360]: [{min_lon}, {max_lon}]")

            time_min = time_max = None
            if has_time:
                try:
                    times = ds["time"].values
                    time_min = str(np.min(times))[:19]
                    time_max = str(np.max(times))[:19]
                except Exception as t_exc:
                    warnings.append(f"Could not parse time range: {t_exc}")

            meta = INCOIS_VERIFIED_DATASETS.get(
                expected_params.dataset_id if expected_params else "ascat_daily_datasets",
                INCOIS_VERIFIED_DATASETS["ascat_daily_datasets"],
            )

            var_summaries: Dict[str, VariableStatsSummary] = {}
            vars_valid = True

            check_vars = (
                expected_params.variables
                if expected_params
                else [v for v in meta.available_variables if v in ds.variables]
            )

            for var_name in check_vars:
                if var_name not in ds.variables:
                    warnings.append(f"Variable '{var_name}' not present in dataset")
                    continue

                da = ds[var_name]
                vals = da.values
                total_pts = int(vals.size)

                is_nan = np.isnan(vals)
                valid_mask = ~is_nan
                valid_count = int(np.count_nonzero(valid_mask))
                missing_count = int(np.count_nonzero(is_nan))

                min_val = max_val = mean_val = std_val = None
                out_of_range = 0

                vmeta = meta.variable_metadata.get(var_name, {})
                vmin = vmeta.get("valid_min")
                vmax = vmeta.get("valid_max")

                if valid_count > 0:
                    v_valid = vals[valid_mask]
                    min_val = round(float(np.min(v_valid)), 4)
                    max_val = round(float(np.max(v_valid)), 4)
                    mean_val = round(float(np.mean(v_valid)), 4)
                    std_val = round(float(np.std(v_valid)), 4)

                    if vmin is not None and min_val < vmin:
                        out_of_range += int(np.count_nonzero(v_valid < vmin))
                    if vmax is not None and max_val > vmax:
                        out_of_range += int(np.count_nonzero(v_valid > vmax))

                    if out_of_range > 0:
                        warnings.append(
                            f"Variable '{var_name}' has {out_of_range} values outside range [{vmin}, {vmax}]"
                        )

                var_summaries[var_name] = VariableStatsSummary(
                    variable_name=var_name,
                    standard_name=vmeta.get("standard_name"),
                    units=vmeta.get("units"),
                    total_points=total_pts,
                    valid_points=valid_count,
                    missing_points=missing_count,
                    out_of_range_points=out_of_range,
                    min_value=min_val,
                    max_value=max_val,
                    mean_value=mean_val,
                    std_value=std_val,
                )

            is_valid = coords_valid and spatial_valid and temporal_valid and (len(errors) == 0)
            status = "VALID" if is_valid and not warnings else ("VALID_WITH_WARNINGS" if is_valid else "FAILED")

            dimensions = {k: int(v) for k, v in ds.dims.items()}

            return UnifiedValidationResult(
                file_path=str(file_path),
                provider_id="incois",
                dataset_id=expected_params.dataset_id if expected_params else "ascat_daily_datasets",
                file_size_bytes=file_size,
                sha256_checksum=sha256_hash,
                is_valid=is_valid,
                status=status,
                spatial_bounds_valid=spatial_valid,
                temporal_bounds_valid=temporal_valid,
                coordinates_valid=coords_valid,
                variables_valid=vars_valid,
                actual_dimensions=dimensions,
                detected_variables=list(ds.variables.keys()),
                variable_statistics=var_summaries,
                spatial_extent={
                    "min_lon": min_lon,
                    "max_lon": max_lon,
                    "min_lat": min_lat,
                    "max_lat": max_lat,
                },
                temporal_extent={
                    "start": time_min,
                    "end": time_max,
                },
                warnings=warnings,
                errors=errors,
            )

    def generate_provenance(
        self,
        retrieval_result: UnifiedRetrievalResult,
        validation_result: Optional[UnifiedValidationResult] = None,
        params: Optional[UnifiedRetrievalParams] = None,
    ) -> UnifiedProvenanceInfo:
        meta = self.get_dataset(retrieval_result.dataset_id)
        return UnifiedProvenanceInfo(
            job_id=retrieval_result.job_id,
            provider_id="incois",
            provider_name="Indian National Centre for Ocean Information Services",
            provider_url=self.base_url,
            dataset_id=retrieval_result.dataset_id,
            dataset_title=meta.product_title,
            retrieval_timestamp=retrieval_result.retrieval_timestamp.isoformat(),
            source_file_url=retrieval_result.raw_metadata.get("query_url", self.base_url),
            file_size_bytes=retrieval_result.file_size_bytes,
            sha256_checksum=retrieval_result.sha256_checksum,
            retrieval_parameters=params.to_dict() if params else {},
            validation_status=validation_result.status if validation_result else "UNVALIDATED",
            licence_information=meta.licence_information or "MoES India Open Access Policy",
            citation=(
                "Data provided by Indian National Centre for Ocean Information Services (INCOIS), "
                "Ministry of Earth Sciences, Government of India. Hyderabad, India. (https://incois.gov.in)"
            ),
            additional_provenance={
                "data_center": "INCOIS Ocean Data and Information System (ODIS)",
                "region": "Indian Ocean Basin",
                "format": "NetCDF-3 Griddap",
            },
        )
