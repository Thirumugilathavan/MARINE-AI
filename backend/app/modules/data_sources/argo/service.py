"""
Argo Ocean Profiling Float Data Provider.

Integrates Euro-Argo / Coriolis Global Data Assembly Centre (GDAC) ERDDAP
services for in-situ vertical oceanographic profiles (temperature, salinity,
pressure) collected by autonomous Argo profiling floats globally.
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

ARGO_BASE_URL = "https://erddap.ifremer.fr/erddap"

ARGO_VERIFIED_DATASETS: Dict[str, ProviderDatasetMeta] = {
    "ArgoFloats": ProviderDatasetMeta(
        provider_id="argo",
        dataset_id="ArgoFloats",
        product_id="CORIOLIS_ARGO_GLOBAL_FLOATS",
        product_title="Argo Global In-Situ Profiling Floats Dataset (Euro-Argo / Coriolis GDAC)",
        dataset_description=(
            "Global dataset of in-situ vertical oceanographic profiles of temperature, "
            "salinity, and pressure collected by autonomous profiling Argo floats distributed "
            "across the world ocean, assembled by Euro-Argo and Coriolis GDAC."
        ),
        available_variables=[
            "temp",
            "psal",
            "pres",
            "temp_qc",
            "psal_qc",
            "pres_qc",
            "platform_number",
            "data_mode",
            "cycle_number",
        ],
        variable_metadata={
            "temp": {
                "standard_name": "sea_water_temperature",
                "units": "degree_C",
                "long_name": "Sea Water In-Situ Temperature",
                "valid_min": -2.5,
                "valid_max": 40.0,
                "qc_flag_name": "temp_qc",
            },
            "psal": {
                "standard_name": "sea_water_practical_salinity",
                "units": "PSU",
                "long_name": "Sea Water Practical Salinity",
                "valid_min": 2.0,
                "valid_max": 42.0,
                "qc_flag_name": "psal_qc",
            },
            "pres": {
                "standard_name": "sea_water_pressure",
                "units": "decibar",
                "long_name": "Sea Water Pressure (Depth Equivalent)",
                "valid_min": 0.0,
                "valid_max": 6500.0,
                "qc_flag_name": "pres_qc",
            },
            "temp_qc": {
                "standard_name": "sea_water_temperature_quality_flag",
                "units": "1",
                "long_name": "Temperature Quality Control Flag",
                "valid_min": 1,
                "valid_max": 9,
            },
            "psal_qc": {
                "standard_name": "sea_water_practical_salinity_quality_flag",
                "units": "1",
                "long_name": "Salinity Quality Control Flag",
                "valid_min": 1,
                "valid_max": 9,
            },
            "pres_qc": {
                "standard_name": "sea_water_pressure_quality_flag",
                "units": "1",
                "long_name": "Pressure Quality Control Flag",
                "valid_min": 1,
                "valid_max": 9,
            },
            "platform_number": {
                "standard_name": "platform_id",
                "units": "1",
                "long_name": "WMO Float Identifier Number",
            },
            "data_mode": {
                "standard_name": "data_mode",
                "units": "1",
                "long_name": "Data Mode (R=Real-time, A=Adjusted, D=Delayed-mode)",
            },
            "cycle_number": {
                "standard_name": "cycle_number",
                "units": "1",
                "long_name": "Float Profile Cycle Number",
            },
        },
        temporal_resolution="in_situ_cycle (~10 days)",
        spatial_resolution="in_situ (~300 km nominal spacing)",
        data_type="in_situ_profile",
        spatial_coverage={"min_lon": -180.0, "max_lon": 180.0, "min_lat": -90.0, "max_lat": 90.0},
        depth_levels_count=None,
        depth_min=0.0,
        depth_max=6000.0,
        time_coverage_start="1999-01-01T00:00:00Z",
        source_documentation="https://www.argo.ucsd.edu/data/argo-data-management/",
        licence_information="CC-BY 4.0 / Argo Data Management Policy (Open & Free Access)",
        verification_status="verified",
    ),
    "ArgoFloats-synthetic-profile": ProviderDatasetMeta(
        provider_id="argo",
        dataset_id="ArgoFloats-synthetic-profile",
        product_id="CORIOLIS_ARGO_BGC_SYNTHETIC",
        product_title="Argo Synthetic Profiles including BioGeoChemical & Core Floats",
        dataset_description="Synthetic Argo profiles collating core T/S and BioGeoChemical variables from Euro-Argo GDAC.",
        available_variables=["temp", "psal", "pres", "doxy", "chla", "bbp700", "platform_number"],
        variable_metadata={
            "temp": {"standard_name": "sea_water_temperature", "units": "degree_C", "valid_min": -2.5, "valid_max": 40.0},
            "psal": {"standard_name": "sea_water_practical_salinity", "units": "PSU", "valid_min": 2.0, "valid_max": 42.0},
            "pres": {"standard_name": "sea_water_pressure", "units": "decibar", "valid_min": 0.0, "valid_max": 6500.0},
            "doxy": {"standard_name": "moles_of_oxygen_per_unit_mass_in_sea_water", "units": "micromole/kg", "valid_min": 0.0, "valid_max": 500.0},
            "chla": {"standard_name": "mass_concentration_of_chlorophyll_a_in_sea_water", "units": "mg/m3", "valid_min": 0.0, "valid_max": 50.0},
        },
        temporal_resolution="in_situ_cycle (~10 days)",
        spatial_resolution="in_situ (~300 km spacing)",
        data_type="in_situ_profile",
        spatial_coverage={"min_lon": -180.0, "max_lon": 180.0, "min_lat": -90.0, "max_lat": 90.0},
        depth_min=0.0,
        depth_max=6000.0,
        time_coverage_start="2000-01-01T00:00:00Z",
        source_documentation="https://www.euro-argo.eu/",
        licence_information="CC-BY 4.0 (Open Access)",
        verification_status="verified",
    ),
}


class ArgoMarineProvider(BaseMarineProvider):
    """
    Argo In-Situ Float Data Provider connecting to Euro-Argo / Coriolis ERDDAP.
    """

    def __init__(self, base_url: str = ARGO_BASE_URL, timeout_seconds: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id="argo",
            name="International Argo Program / Euro-Argo",
            organization="Euro-Argo ERIC & Coriolis Global Data Assembly Centre (GDAC)",
            base_url=self.base_url,
            documentation_url="https://www.argo.ucsd.edu/",
            access_method="erddap_tabledap",
            authentication_required=False,
            auth_description="Public open access. Global profiling float program under IOC-UNESCO and WMO.",
            status="operational",
            supported_formats=["NetCDF-3", "NetCDF-4", "CSV", "JSON"],
            rate_limits_info="Standard fair-use ERDDAP policy (< 10 concurrent requests)",
            licence_info="Argo Data Policy / CC-BY 4.0: Data freely available without restriction.",
        )

    def list_datasets(self) -> List[ProviderDatasetMeta]:
        return list(ARGO_VERIFIED_DATASETS.values())

    def get_dataset(self, dataset_id: str) -> ProviderDatasetMeta:
        if dataset_id not in ARGO_VERIFIED_DATASETS:
            raise DatasetNotFoundError(
                f"Dataset '{dataset_id}' not found in Argo catalogue. "
                f"Available datasets: {list(ARGO_VERIFIED_DATASETS.keys())}"
            )
        return ARGO_VERIFIED_DATASETS[dataset_id]

    def search_catalogue(
        self,
        query: str,
        variables: Optional[List[str]] = None,
        data_type: Optional[str] = None,
    ) -> List[ProviderDatasetMeta]:
        results = []
        q = query.lower()
        for meta in ARGO_VERIFIED_DATASETS.values():
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
                f"Unknown variable(s) {unknown_vars} for Argo dataset '{params.dataset_id}'. "
                f"Available: {meta.available_variables}"
            )

        # Validate longitude bounds [-180, 180] or [0, 360]
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

        # Validate depth if specified
        if params.minimum_depth is not None and params.minimum_depth < 0:
            raise InvalidBoundsError(f"minimum_depth ({params.minimum_depth}) cannot be negative")
        if params.maximum_depth is not None and params.maximum_depth > 6500:
            raise InvalidBoundsError(f"maximum_depth ({params.maximum_depth}) exceeds maximum Argo depth (6500 dbar)")
        if (
            params.minimum_depth is not None
            and params.maximum_depth is not None
            and params.minimum_depth > params.maximum_depth
        ):
            raise InvalidBoundsError(f"minimum_depth ({params.minimum_depth}) > maximum_depth ({params.maximum_depth})")

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

        # Argo floats are sparsely distributed (~1 float per 300x300 km box, ~3000 profiles/month globally)
        # Average profiling frequency: 1 cycle per 10 days per float
        # Estimate ~0.005 profiles per deg2 per day
        estimated_profiles = max(1, int(bbox_area * duration_days * 0.005))
        # Each profile has ~100-200 depth levels
        estimated_total_points = estimated_profiles * 150 * len(validated.variables)
        estimated_size_mb = round(max(0.05, estimated_total_points * 16 / (1024 * 1024)), 3)

        return UnifiedPreviewResult(
            request_id=request_id,
            provider_id="argo",
            dataset_id=validated.dataset_id,
            estimated_size_mb=estimated_size_mb,
            estimated_total_points=estimated_total_points,
            bounding_box_area_deg2=bbox_area,
            duration_days=round(duration_days, 2),
            status="success",
            message=(
                f"Valid Argo in-situ parameters. Bounding area: {bbox_area} deg², "
                f"duration: {round(duration_days, 1)} days. Estimated ~{estimated_profiles} profiles."
            ),
            selected_extent={
                "min_lon": validated.minimum_longitude,
                "max_lon": validated.maximum_longitude,
                "min_lat": validated.minimum_latitude,
                "max_lat": validated.maximum_latitude,
                "start_time": validated.start_datetime,
                "end_time": validated.end_datetime,
                "min_depth": validated.minimum_depth,
                "max_depth": validated.maximum_depth,
            },
            variables=validated.variables,
        )

    def _build_tabledap_url(self, params: UnifiedRetrievalParams) -> str:
        """
        Constructs the ERDDAP tabledap query URL for Argo in-situ profiles.
        Tabledap format:
        /tabledap/{datasetID}.nc?var1,var2,...&constraints
        """
        # Always request coordinates and tracking variables
        base_vars = ["latitude", "longitude", "time", "platform_number", "cycle_number", "data_mode"]
        requested_vars = list(params.variables)

        # For any core measurement, include its QC flag if present
        extra_qcs = []
        for v in requested_vars:
            if v == "temp" and "temp_qc" not in requested_vars:
                extra_qcs.append("temp_qc")
            elif v == "psal" and "psal_qc" not in requested_vars:
                extra_qcs.append("psal_qc")
            elif v == "pres" and "pres_qc" not in requested_vars:
                extra_qcs.append("pres_qc")

        # Combine uniquely
        all_vars = []
        for v in base_vars + requested_vars + extra_qcs:
            if v not in all_vars:
                all_vars.append(v)

        vars_str = ",".join(all_vars)

        # Format ISO datetimes
        start_t = params.start_datetime if "T" in params.start_datetime else f"{params.start_datetime}T00:00:00Z"
        end_t = params.end_datetime if "T" in params.end_datetime else f"{params.end_datetime}T23:59:59Z"
        if not start_t.endswith("Z") and not "+" in start_t:
            start_t += "Z"
        if not end_t.endswith("Z") and not "+" in end_t:
            end_t += "Z"

        constraints = [
            f"latitude>={params.minimum_latitude}",
            f"latitude<={params.maximum_latitude}",
            f"longitude>={params.minimum_longitude}",
            f"longitude<={params.maximum_longitude}",
            f'time>="{start_t}"',
            f'time<="{end_t}"',
        ]

        if params.minimum_depth is not None:
            constraints.append(f"pres>={params.minimum_depth}")
        if params.maximum_depth is not None:
            constraints.append(f"pres<={params.maximum_depth}")

        constraints_str = "&".join(constraints)
        url = f"{self.base_url}/tabledap/{params.dataset_id}.nc?{vars_str}&{constraints_str}"
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
        jid = job_id or f"argo-job-{uuid.uuid4().hex[:12]}"

        target_dir = staging_dir or output_dir or Path("dataset-staging/argo")
        job_dir = target_dir / jid if jid not in str(target_dir) else target_dir
        job_dir.mkdir(parents=True, exist_ok=True)

        filename = validated.output_filename or f"argo_{validated.dataset_id}_{jid[:8]}.nc"
        file_path = job_dir / filename

        query_url = self._build_tabledap_url(validated)
        logger.info("Executing Argo ERDDAP query: %s", query_url)

        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.get(query_url)

                if response.status_code == 404:
                    # ERDDAP returns 404 when no data rows match the query
                    raise RetrievalError(
                        f"No Argo float profiles found matching criteria in dataset '{validated.dataset_id}' "
                        f"(lat [{validated.minimum_latitude}, {validated.maximum_latitude}], "
                        f"lon [{validated.minimum_longitude}, {validated.maximum_longitude}], "
                        f"time [{validated.start_datetime}, {validated.end_datetime}]). "
                        "Try expanding spatial or temporal bounds."
                    )
                elif response.status_code != 200:
                    err_msg = response.text[:400]
                    raise RetrievalError(
                        f"Argo ERDDAP request failed with HTTP {response.status_code}: {err_msg}"
                    )

                content = response.content
                file_path.write_bytes(content)

        except httpx.RequestError as exc:
            raise RetrievalError(f"Network error querying Argo ERDDAP: {exc}") from exc

        file_size = file_path.stat().st_size
        sha256_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

        return UnifiedRetrievalResult(
            job_id=jid,
            provider_id="argo",
            dataset_id=validated.dataset_id,
            file_path=file_path,
            file_format="NetCDF-3",
            file_size_bytes=file_size,
            sha256_checksum=sha256_hash,
            raw_metadata={
                "query_url": query_url,
                "retrieved_bytes": file_size,
                "provider": "Euro-Argo / Coriolis GDAC",
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
                provider_id="argo",
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
            # Check coordinates in Tabledap (usually 1D variables along 'row' dimension)
            has_lat = "latitude" in ds.variables
            has_lon = "longitude" in ds.variables
            has_time = "time" in ds.variables
            coords_valid = has_lat and has_lon and has_time

            total_rows = 0
            if "row" in ds.dims:
                total_rows = int(ds.dims["row"])
            elif has_lat:
                total_rows = len(ds["latitude"])

            if total_rows == 0:
                warnings.append("Dataset contains 0 observation rows.")

            spatial_valid = True
            temporal_valid = True

            min_lon = max_lon = min_lat = max_lat = None
            if has_lat and total_rows > 0:
                lats = ds["latitude"].values
                valid_lats = lats[~np.isnan(lats)]
                if len(valid_lats) > 0:
                    min_lat = float(np.min(valid_lats))
                    max_lat = float(np.max(valid_lats))
                    if min_lat < -90.0 or max_lat > 90.0:
                        spatial_valid = False
                        errors.append(f"Latitude bounds out of physical range [-90, 90]: [{min_lat}, {max_lat}]")

            if has_lon and total_rows > 0:
                lons = ds["longitude"].values
                valid_lons = lons[~np.isnan(lons)]
                if len(valid_lons) > 0:
                    min_lon = float(np.min(valid_lons))
                    max_lon = float(np.max(valid_lons))
                    if min_lon < -180.0 or max_lon > 360.0:
                        spatial_valid = False
                        errors.append(f"Longitude bounds out of range [-180, 360]: [{min_lon}, {max_lon}]")

            time_min = time_max = None
            if has_time and total_rows > 0:
                try:
                    times = ds["time"].values
                    time_min = str(np.min(times))[:19]
                    time_max = str(np.max(times))[:19]
                except Exception as t_exc:
                    warnings.append(f"Could not parse time range: {t_exc}")

            # Check variables & calculate statistics
            meta = ARGO_VERIFIED_DATASETS.get(
                expected_params.dataset_id if expected_params else "ArgoFloats",
                ARGO_VERIFIED_DATASETS["ArgoFloats"],
            )

            var_summaries: Dict[str, VariableStatsSummary] = {}
            vars_valid = True

            # Identify variables to validate
            check_vars = (
                expected_params.variables
                if expected_params
                else [v for v in ["temp", "psal", "pres"] if v in ds.variables]
            )

            for var_name in check_vars:
                if var_name not in ds.variables:
                    warnings.append(f"Variable '{var_name}' not present in retrieved file")
                    continue

                da = ds[var_name]
                vals = da.values
                total_pts = int(vals.size)

                # Missing values
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
                            f"Variable '{var_name}' has {out_of_range} values outside plausible range [{vmin}, {vmax}]"
                        )

                # QC Flag distributions if companion QC variable exists
                qc_counts: Dict[str, int] = {}
                qc_var_name = vmeta.get("qc_flag_name") or f"{var_name}_qc"
                if qc_var_name in ds.variables:
                    qc_vals = ds[qc_var_name].values
                    # QC flag definitions: 1=good, 2=probably good, 3=probably bad, 4=bad, 9=missing
                    for flag_val in [1, 2, 3, 4, 9]:
                        flag_count = int(np.count_nonzero(qc_vals == flag_val))
                        if flag_count > 0:
                            qc_counts[f"flag_{flag_val}"] = flag_count

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
                    qc_flag_counts=qc_counts,
                )

            # Unique WMO float count
            platforms_count = 0
            if "platform_number" in ds.variables:
                p_vals = ds["platform_number"].values
                platforms_count = len(np.unique(p_vals))

            # Data mode breakdown
            data_modes: Dict[str, int] = {}
            if "data_mode" in ds.variables:
                dm_vals = ds["data_mode"].values
                for m in ["R", "A", "D"]:
                    cnt = int(np.count_nonzero(dm_vals == m))
                    if cnt > 0:
                        data_modes[m] = cnt

            is_valid = coords_valid and spatial_valid and temporal_valid and (len(errors) == 0)
            status = "VALID" if is_valid and not warnings else ("VALID_WITH_WARNINGS" if is_valid else "FAILED")

            dimensions = {k: int(v) for k, v in ds.dims.items()}

            return UnifiedValidationResult(
                file_path=str(file_path),
                provider_id="argo",
                dataset_id=expected_params.dataset_id if expected_params else "ArgoFloats",
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
                additional_metadata={
                    "total_profiles_rows": total_rows,
                    "unique_wmo_platforms_count": platforms_count,
                    "data_modes_distribution": data_modes,
                },
            )

    def generate_provenance(
        self,
        retrieval_result: UnifiedRetrievalResult,
        validation_result: Optional[UnifiedValidationResult] = None,
        params: Optional[UnifiedRetrievalParams] = None,
    ) -> UnifiedProvenanceInfo:
        meta = self.get_dataset(retrieval_result.dataset_id)
        wmo_count = 0
        if validation_result and validation_result.additional_metadata:
            wmo_count = validation_result.additional_metadata.get("unique_wmo_platforms_count", 0)

        return UnifiedProvenanceInfo(
            job_id=retrieval_result.job_id,
            provider_id="argo",
            provider_name="International Argo Program / Euro-Argo",
            provider_url=self.base_url,
            dataset_id=retrieval_result.dataset_id,
            dataset_title=meta.product_title,
            retrieval_timestamp=retrieval_result.retrieval_timestamp.isoformat(),
            source_file_url=retrieval_result.raw_metadata.get("query_url", self.base_url),
            file_size_bytes=retrieval_result.file_size_bytes,
            sha256_checksum=retrieval_result.sha256_checksum,
            retrieval_parameters=params.to_dict() if params else {},
            validation_status=validation_result.status if validation_result else "UNVALIDATED",
            licence_information=meta.licence_information or "CC-BY 4.0 / Argo Data Policy",
            citation=(
                "These data were collected and made freely available by the International Argo Program "
                "and the national programs that contribute to it (https://argo.ucsd.edu, https://www.ocean-ops.org). "
                "The Argo Program is part of the Global Ocean Observing System (GOOS)."
            ),
            additional_provenance={
                "wmo_platforms_observed": wmo_count,
                "assembly_centre": "Euro-Argo ERIC / Coriolis GDAC",
                "format": "NetCDF-3 Tabledap In-Situ Ocean Profiles",
            },
        )
