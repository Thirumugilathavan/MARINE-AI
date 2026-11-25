"""
NOAA (National Oceanic and Atmospheric Administration) Data Provider.

Integrates NOAA ERDDAP services (CoastWatch / NCEI) for gridded Sea Surface
Temperature (OISST v2.1) and oceanographic observations.
"""

from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re
from typing import Dict, List, Optional, Any
import urllib.parse
import uuid

import httpx
import numpy as np
import xarray as xr

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

NOAA_BASE_URL = "https://coastwatch.pfeg.noaa.gov/erddap"

NOAA_VERIFIED_DATASETS: Dict[str, ProviderDatasetMeta] = {
    "ncdcOisst21Agg_LonPM180": ProviderDatasetMeta(
        provider_id="noaa",
        dataset_id="ncdcOisst21Agg_LonPM180",
        product_id="NOAA_OISST_V2_1_FINAL",
        product_title="NOAA 1/4° Daily Optimum Interpolation Sea Surface Temperature (OISST) v2.1",
        dataset_description=(
            "NOAA 0.25-degree daily Optimum Interpolation Sea Surface Temperature (OISST) v2.1 "
            "constructed by combining observations from satellites (AVHRR) and in-situ platforms (ships, buoys)."
        ),
        available_variables=["sst", "anom", "err", "ice"],
        variable_metadata={
            "sst": {
                "standard_name": "sea_surface_temperature",
                "units": "degree_C",
                "long_name": "Daily Sea Surface Temperature",
                "valid_min": -3.0,
                "valid_max": 45.0,
            },
            "anom": {
                "standard_name": "sea_surface_temperature_anomaly",
                "units": "degree_C",
                "long_name": "Daily Sea Surface Temperature Anomaly",
                "valid_min": -15.0,
                "valid_max": 15.0,
            },
            "err": {
                "standard_name": "sea_surface_temperature_error",
                "units": "degree_C",
                "long_name": "Estimated Error of Daily Sea Surface Temperature",
                "valid_min": 0.0,
                "valid_max": 10.0,
            },
            "ice": {
                "standard_name": "sea_ice_area_fraction",
                "units": "1",
                "long_name": "Daily Sea Ice Concentration",
                "valid_min": 0.0,
                "valid_max": 1.0,
            },
        },
        temporal_resolution="daily",
        spatial_resolution="0.25 degree (~27 km)",
        data_type="satellite_observation_analysis",
        spatial_coverage={"min_lon": -180.0, "max_lon": 180.0, "min_lat": -90.0, "max_lat": 90.0},
        depth_levels_count=1,
        depth_min=0.0,
        depth_max=0.0,
        time_coverage_start="1981-09-01T12:00:00Z",
        source_documentation="https://www.ncei.noaa.gov/products/optimum-interpolation-sst",
        licence_information="US Government Open Data / Public Domain",
        verification_status="verified",
    )
}


class NOAAMarineProvider(BaseMarineProvider):
    """
    NOAA implementation of BaseMarineProvider connecting to NOAA ERDDAP services.
    """

    def __init__(self, base_url: str = NOAA_BASE_URL, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._metadata = ProviderMetadata(
            provider_id="noaa",
            name="National Oceanic and Atmospheric Administration",
            organization="NOAA CoastWatch / NCEI / SWFSC",
            base_url=self.base_url,
            documentation_url="https://coastwatch.pfeg.noaa.gov/erddap/information.html",
            access_method="erddap_griddap_rest",
            authentication_required=False,
            auth_description="No authentication required. Public domain open scientific data.",
            status="active",
            supported_formats=["NetCDF-3", "NetCDF-4", "JSON", "CSV"],
            rate_limits_info="Fair use policy (recommend max 1 request/second per client)",
            licence_info="Public Domain / Open Data Policy (NOAA NCEI)",
        )

    def metadata(self) -> ProviderMetadata:
        return self._metadata

    def list_datasets(self) -> List[ProviderDatasetMeta]:
        return list(NOAA_VERIFIED_DATASETS.values())

    def get_dataset(self, dataset_id: str) -> ProviderDatasetMeta:
        if dataset_id not in NOAA_VERIFIED_DATASETS:
            raise DatasetNotFoundError(
                f"Dataset '{dataset_id}' not found in NOAA provider registry. "
                f"Available: {list(NOAA_VERIFIED_DATASETS.keys())}"
            )
        return NOAA_VERIFIED_DATASETS[dataset_id]

    def search_catalogue(self, keyword: str, limit: int = 10) -> Dict[str, Any]:
        """Queries the live NOAA CoastWatch ERDDAP catalogue search endpoint."""
        url = f"{self.base_url}/search/index.json"
        params = {"searchFor": keyword}

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            rows = data.get("table", {}).get("rows", [])
            col_names = data.get("table", {}).get("columnNames", [])
            id_idx = col_names.index("Dataset ID") if "Dataset ID" in col_names else 0
            title_idx = col_names.index("Title") if "Title" in col_names else 1
            summary_idx = col_names.index("Summary") if "Summary" in col_names else -1

            products = []
            for row in rows[:limit]:
                p_id = row[id_idx]
                p_title = row[title_idx]
                p_summary = row[summary_idx] if summary_idx >= 0 and len(row) > summary_idx else ""
                products.append({
                    "product_id": p_id,
                    "dataset_id": p_id,
                    "title": p_title,
                    "description": p_summary,
                    "provider": "NOAA CoastWatch",
                })

            return {
                "provider": "noaa",
                "total_found": len(rows),
                "returned": len(products),
                "products": products,
            }
        except Exception as exc:
            logger.error(f"NOAA catalogue search failed: {exc}")
            raise RetrievalError(f"NOAA catalogue search error: {exc}") from exc

    def validate_parameters(self, params: UnifiedRetrievalParams) -> None:
        """Validates geographic, variable, and temporal safety bounds."""
        dataset = self.get_dataset(params.dataset_id)

        # 1. Variables
        for var in params.variables:
            if var not in dataset.available_variables:
                raise InvalidVariableError(
                    f"Variable '{var}' is not available in NOAA dataset '{params.dataset_id}'. "
                    f"Available: {dataset.available_variables}"
                )

        # 2. Coordinates
        if not (-180.0 <= params.minimum_longitude <= 180.0):
            raise InvalidBoundsError(f"minimum_longitude {params.minimum_longitude} out of range [-180, 180]")
        if not (-180.0 <= params.maximum_longitude <= 180.0):
            raise InvalidBoundsError(f"maximum_longitude {params.maximum_longitude} out of range [-180, 180]")
        if not (-90.0 <= params.minimum_latitude <= 90.0):
            raise InvalidBoundsError(f"minimum_latitude {params.minimum_latitude} out of range [-90, 90]")
        if not (-90.0 <= params.maximum_latitude <= 90.0):
            raise InvalidBoundsError(f"maximum_latitude {params.maximum_latitude} out of range [-90, 90]")

        if params.minimum_longitude > params.maximum_longitude:
            raise InvalidBoundsError(
                f"minimum_longitude ({params.minimum_longitude}) must be <= maximum_longitude ({params.maximum_longitude})"
            )
        if params.minimum_latitude > params.maximum_latitude:
            raise InvalidBoundsError(
                f"minimum_latitude ({params.minimum_latitude}) must be <= maximum_latitude ({params.maximum_latitude})"
            )

        # 3. Area limit
        lon_span = params.maximum_longitude - params.minimum_longitude
        lat_span = params.maximum_latitude - params.minimum_latitude
        area_deg2 = lon_span * lat_span
        if area_deg2 > 2500.0:
            raise InvalidBoundsError(
                f"Requested bounding box area ({area_deg2:.1f} deg²) exceeds safety limit (2500.0 deg²)."
            )

        # 4. Temporal range
        try:
            start_dt = datetime.fromisoformat(params.start_datetime.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(params.end_datetime.replace("Z", "+00:00"))
        except Exception as exc:
            raise InvalidBoundsError(f"Invalid ISO 8601 datetime format: {exc}")

        if start_dt > end_dt:
            raise InvalidBoundsError("start_datetime must be <= end_datetime")

        duration_days = (end_dt - start_dt).total_seconds() / 86400.0
        if duration_days > 365.0:
            raise InvalidBoundsError("Requested duration exceeds maximum allowed limit of 365 days.")

        return params

    def preview(self, params: UnifiedRetrievalParams, request_id: Optional[str] = None) -> UnifiedPreviewResult:
        """Executes a bounded dry-run preview estimating grid points and payload volume."""
        self.validate_parameters(params)
        req_id = request_id or str(uuid.uuid4())

        lon_span = abs(params.maximum_longitude - params.minimum_longitude)
        lat_span = abs(params.maximum_latitude - params.minimum_latitude)
        area_deg2 = lon_span * lat_span

        start_dt = datetime.fromisoformat(params.start_datetime.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(params.end_datetime.replace("Z", "+00:00"))
        duration_days = max(1.0, (end_dt - start_dt).total_seconds() / 86400.0)

        # Estimate grid points for 0.25° resolution
        res_deg = 0.25
        lon_pts = max(1, int(round(lon_span / res_deg)) + 1)
        lat_pts = max(1, int(round(lat_span / res_deg)) + 1)
        time_pts = max(1, int(round(duration_days)))
        total_pts = lon_pts * lat_pts * time_pts * len(params.variables)

        # Approx 4 bytes per float point + 4KB NetCDF metadata overhead
        estimated_size_mb = round((total_pts * 4 + 4096) / (1024 * 1024), 4)

        return UnifiedPreviewResult(
            request_id=req_id,
            provider_id="noaa",
            dataset_id=params.dataset_id,
            estimated_size_mb=estimated_size_mb,
            estimated_total_points=total_pts,
            bounding_box_area_deg2=round(area_deg2, 4),
            duration_days=round(duration_days, 2),
            status="success",
            message=f"NOAA dry-run preview succeeded for {total_pts} estimated grid points.",
            selected_extent={
                "longitude": {"min": params.minimum_longitude, "max": params.maximum_longitude, "unit": "degrees_east"},
                "latitude": {"min": params.minimum_latitude, "max": params.maximum_latitude, "unit": "degrees_north"},
                "time": {"start": params.start_datetime, "end": params.end_datetime, "unit": "iso8601"},
            },
            variables=params.variables,
        )

    def retrieve(
        self,
        params: UnifiedRetrievalParams,
        job_id: str,
        staging_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        **kwargs,
    ) -> UnifiedRetrievalResult:
        """Downloads a bounded NetCDF subset from NOAA ERDDAP griddap."""
        self.validate_parameters(params)

        target_dir = staging_dir or output_dir or Path("dataset-staging/noaa")
        job_dir = target_dir / job_id if job_id not in str(target_dir) else target_dir
        job_dir.mkdir(parents=True, exist_ok=True)

        filename = params.output_filename or f"noaa_{params.dataset_id}_{job_id[:8]}.nc"
        # Sanitize filename
        clean_name = Path(filename).name
        clean_name = re.sub(r"[^\w\-.]", "_", clean_name)
        if not clean_name.endswith(".nc"):
            clean_name += ".nc"
        target_path = job_dir / clean_name

        # Construct ERDDAP griddap query
        # Format: dataset.nc?var1[(start):(end)][(zlev)][(min_lat):(max_lat)][(min_lon):(max_lon)],var2...
        var_clauses = []
        for var in params.variables:
            clause = (
                f"{var}"
                f"[({params.start_datetime}):({params.end_datetime})]"
                f"[(0.0)]"
                f"[({params.minimum_latitude}):({params.maximum_latitude})]"
                f"[({params.minimum_longitude}):({params.maximum_longitude})]"
            )
            # URL encode bracket syntax for strict HTTP servers
            encoded_clause = urllib.parse.quote(clause, safe=":=,")
            var_clauses.append(encoded_clause)

        query_str = ",".join(var_clauses)
        download_url = f"{self.base_url}/griddap/{params.dataset_id}.nc?{query_str}"
        logger.info(f"[Job {job_id}] Requesting NOAA subset from: {download_url}")

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
                resp = client.get(download_url)
                if resp.status_code != 200:
                    raise RetrievalError(
                        f"NOAA ERDDAP request failed with HTTP {resp.status_code}: {resp.text[:300]}"
                    )
                target_path.write_bytes(resp.content)

            file_size = target_path.stat().st_size
            sha256_hash = hashlib.sha256(resp.content).hexdigest()

            return UnifiedRetrievalResult(
                job_id=job_id,
                provider_id="noaa",
                dataset_id=params.dataset_id,
                file_path=target_path,
                file_format="NetCDF-3",
                file_size_bytes=file_size,
                sha256_checksum=sha256_hash,
                raw_metadata={"source_url": download_url, "erddap_status": resp.status_code},
            )
        except Exception as exc:
            logger.error(f"[Job {job_id}] NOAA retrieval failed: {exc}")
            raise RetrievalError(f"NOAA subset retrieval failed: {exc}") from exc

    def validate_data(
        self,
        file_path: Path,
        params: UnifiedRetrievalParams,
    ) -> UnifiedValidationResult:
        """Validates NetCDF format, CF conventions, coordinate structure, and physical plausibility."""
        path = Path(file_path)
        if not path.exists() or path.stat().st_size == 0:
            return UnifiedValidationResult(
                file_path=str(path),
                provider_id="noaa",
                dataset_id=params.dataset_id,
                status="failed",
                is_valid=False,
                errors=[f"File does not exist or is empty: {path}"],
            )

        try:
            ds = xr.open_dataset(path)
        except Exception as exc:
            return UnifiedValidationResult(
                file_path=str(path),
                provider_id="noaa",
                dataset_id=params.dataset_id,
                status="failed",
                is_valid=False,
                errors=[f"Failed to open NetCDF with xarray: {exc}"],
            )

        warnings: List[str] = []
        errors: List[str] = []
        var_stats: Dict[str, VariableStatsSummary] = {}

        try:
            cf_conv = ds.attrs.get("Conventions", "CF-1.6")
            dims_dict = {str(k): int(v) for k, v in ds.sizes.items()}

            coords_summary = {}
            for coord in ["time", "zlev", "latitude", "longitude"]:
                if coord in ds.coords:
                    c_vals = ds[coord].values
                    coords_summary[coord] = {
                        "size": int(c_vals.size),
                        "min": float(c_vals.min()) if np.issubdtype(c_vals.dtype, np.number) else str(c_vals.min()),
                        "max": float(c_vals.max()) if np.issubdtype(c_vals.dtype, np.number) else str(c_vals.max()),
                    }

            dataset_meta = self.get_dataset(params.dataset_id)

            for var_name in params.variables:
                if var_name not in ds.data_vars:
                    errors.append(f"Expected variable '{var_name}' not present in downloaded NOAA file.")
                    continue

                da = ds[var_name]
                raw_arr = da.values
                float_arr = np.asarray(raw_arr, dtype=float)
                total_pts = int(float_arr.size)
                nan_mask = np.isnan(float_arr)
                nan_count = int(np.sum(nan_mask))
                valid_count = total_pts - nan_count

                v_meta = dataset_meta.variable_metadata.get(var_name, {})
                units = da.attrs.get("units", v_meta.get("units", "unknown"))
                std_name = da.attrs.get("standard_name", v_meta.get("standard_name"))

                v_stat = VariableStatsSummary(
                    variable_name=var_name,
                    standard_name=std_name,
                    units=units,
                    total_points=total_pts,
                    valid_points=valid_count,
                    missing_points=nan_count,
                )

                if valid_count > 0:
                    valid_vals = float_arr[~nan_mask]
                    v_stat.min_value = float(np.min(valid_vals))
                    v_stat.max_value = float(np.max(valid_vals))
                    v_stat.mean_value = float(np.mean(valid_vals))
                    v_stat.std_value = float(np.std(valid_vals))

                    # Physical bounds check
                    v_min = v_meta.get("valid_min", -3.0)
                    v_max = v_meta.get("valid_max", 45.0)
                    oob = np.sum((valid_vals < v_min) | (valid_vals > v_max))
                    v_stat.out_of_range_points = int(oob)
                    if oob > 0:
                        msg = f"Variable '{var_name}': {oob} points outside plausibility range [{v_min}, {v_max}] {units}"
                        v_stat.warnings.append(msg)
                        warnings.append(msg)
                else:
                    msg = f"Variable '{var_name}': all points are masked or NaN (e.g. land points)."
                    v_stat.warnings.append(msg)
                    warnings.append(msg)

                var_stats[var_name] = v_stat

        finally:
            ds.close()

        status = "passed"
        is_valid = True
        if errors:
            status = "failed"
            is_valid = False
        elif warnings:
            status = "warnings"

        return UnifiedValidationResult(
            file_path=str(path),
            provider_id="noaa",
            dataset_id=params.dataset_id,
            status=status,
            is_valid=is_valid,
            dimensions=dims_dict,
            coordinates_summary=coords_summary,
            variable_stats=var_stats,
            cf_conventions=cf_conv,
            warnings=warnings,
            errors=errors,
        )

    def generate_provenance(
        self,
        retrieval_result: Any,
        validation_result: Optional[UnifiedValidationResult] = None,
        params: Optional[UnifiedRetrievalParams] = None,
        job_id: Optional[str] = None,
        **kwargs,
    ) -> UnifiedProvenanceInfo:
        # Handle flexible argument orders
        if isinstance(retrieval_result, str):
            # Signature was: (job_id, retrieval_result, validation_result, params)
            effective_job_id = retrieval_result
            r_res = validation_result  # type: ignore
            v_res = params  # type: ignore
            p_params = kwargs.get("params") or params
        else:
            r_res = retrieval_result
            effective_job_id = job_id or (r_res.job_id if hasattr(r_res, "job_id") else "unknown-job")
            v_res = validation_result
            p_params = params

        dataset_id = p_params.dataset_id if p_params else (r_res.dataset_id if hasattr(r_res, "dataset_id") else "ncdcOisst21Agg_LonPM180")
        dataset = self.get_dataset(dataset_id)
        
        v_stats = v_res.variable_stats if (v_res and hasattr(v_res, "variable_stats")) else {}
        units_dict = {v: v_stats[v].units or "unknown" for v in v_stats} if v_stats else {}

        time_ext = (v_res.temporal_extent if hasattr(v_res, "temporal_extent") else {}) or {}
        spat_ext = (v_res.spatial_extent if hasattr(v_res, "spatial_extent") else {}) or {}
        if not spat_ext and v_res and hasattr(v_res, "coordinates_summary"):
            spat_ext = v_res.coordinates_summary

        return UnifiedProvenanceInfo(
            job_id=effective_job_id,
            provider="National Oceanic and Atmospheric Administration",
            product_id=dataset.product_id,
            dataset_id=dataset_id,
            dataset_version="2.1",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            requested_date_range={
                "start": p_params.start_datetime if p_params else "",
                "end": p_params.end_datetime if p_params else "",
            },
            actual_data_date_range=time_ext,
            spatial_extent=spat_ext,
            variables=p_params.variables if p_params else list(v_stats.keys()),
            units=units_dict,
            processing_method="noaa_erddap_griddap_rest",
            source_licence=dataset.licence_information,
            toolbox_version="MARINE-AI-Unified-1.0",
            sha256_checksum=r_res.sha256_checksum if hasattr(r_res, "sha256_checksum") else "",
            validation_report_id=None,
        )


noaa_provider = NOAAMarineProvider()
