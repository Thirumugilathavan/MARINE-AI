"""
NetCDF and oceanographic data validation module using xarray.

Validates dimensions, coordinates, bounds, CF conventions, units,
missing/NaN patterns, physical sanity, and statistical distributions.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
import numpy as np
import xarray as xr

from app.modules.data_sources.copernicus.dataset_registry import registry, RegisteredDataset


@dataclass
class VariableStats:
    variable_name: str
    standard_name: Optional[str] = None
    units: Optional[str] = None
    total_points: int = 0
    valid_points: int = 0
    missing_points: int = 0  # NaN or masked
    out_of_range_points: int = 0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    std_value: Optional[float] = None
    is_valid: bool = True
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    file_path: str
    status: str  # "passed", "warnings", "failed"
    is_valid: bool
    cf_conventions: Optional[str] = None
    dimensions: Dict[str, int] = field(default_factory=dict)
    coordinates_summary: Dict[str, Any] = field(default_factory=dict)
    variable_stats: Dict[str, VariableStats] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NetCDFValidator:
    """
    Validates Copernicus NetCDF output files against CF conventions,
    spatial-temporal bounds, and registry metadata.
    """

    def __init__(self, tolerance_deg: float = 0.15):
        # Tolerance allows for grid cell discretization differences
        self.tolerance_deg = tolerance_deg

    def validate_file(
        self,
        file_path: Path | str,
        expected_dataset_id: Optional[str] = None,
        expected_variables: Optional[List[str]] = None,
        expected_bounds: Optional[Dict[str, float]] = None,
        expected_start_time: Optional[str] = None,
        expected_end_time: Optional[str] = None,
        expected_depth_min: Optional[float] = None,
        expected_depth_max: Optional[float] = None,
    ) -> ValidationReport:
        path = Path(file_path)

        # 1. File exists
        if not path.exists():
            return ValidationReport(
                file_path=str(path),
                status="failed",
                is_valid=False,
                errors=[f"File not found: {path}"],
            )

        # 2. File is readable
        if not path.is_file() or path.stat().st_size == 0:
            return ValidationReport(
                file_path=str(path),
                status="failed",
                is_valid=False,
                errors=[f"File is empty or not a regular file: {path}"],
            )

        # 3. Valid NetCDF dataset
        try:
            ds = xr.open_dataset(path)
        except Exception as exc:
            return ValidationReport(
                file_path=str(path),
                status="failed",
                is_valid=False,
                errors=[f"Failed to open file as NetCDF with xarray: {exc}"],
            )

        warnings: List[str] = []
        errors: List[str] = []
        var_stats: Dict[str, VariableStats] = {}

        try:
            # 4. Check CF Conventions and global metadata
            cf_conv = ds.attrs.get("Conventions", None)
            if not cf_conv:
                warnings.append("Global attribute 'Conventions' is missing.")

            # 5. Extract Dimensions
            dims_dict = {str(k): int(v) for k, v in ds.sizes.items()}

            # 6. Extract Coordinates summary
            coords_summary: Dict[str, Any] = {}
            for coord_name in ["longitude", "latitude", "time", "depth"]:
                if coord_name in ds.coords:
                    c_vals = ds[coord_name].values
                    if c_vals.size > 0:
                        coords_summary[coord_name] = {
                            "size": int(c_vals.size),
                            "min": float(np.min(c_vals)) if np.issubdtype(c_vals.dtype, np.number) else str(np.min(c_vals)),
                            "max": float(np.max(c_vals)) if np.issubdtype(c_vals.dtype, np.number) else str(np.max(c_vals)),
                        }

            # 7. Check expected bounds if provided
            if expected_bounds:
                if "longitude" in ds.coords:
                    lons = ds["longitude"].values
                    req_min_lon = expected_bounds.get("minimum_longitude")
                    req_max_lon = expected_bounds.get("maximum_longitude")
                    if req_min_lon is not None and np.min(lons) < req_min_lon - self.tolerance_deg:
                        warnings.append(f"Longitude minimum ({np.min(lons):.3f}) is outside requested minimum ({req_min_lon})")
                    if req_max_lon is not None and np.max(lons) > req_max_lon + self.tolerance_deg:
                        warnings.append(f"Longitude maximum ({np.max(lons):.3f}) is outside requested maximum ({req_max_lon})")

                if "latitude" in ds.coords:
                    lats = ds["latitude"].values
                    req_min_lat = expected_bounds.get("minimum_latitude")
                    req_max_lat = expected_bounds.get("maximum_latitude")
                    if req_min_lat is not None and np.min(lats) < req_min_lat - self.tolerance_deg:
                        warnings.append(f"Latitude minimum ({np.min(lats):.3f}) is outside requested minimum ({req_min_lat})")
                    if req_max_lat is not None and np.max(lats) > req_max_lat + self.tolerance_deg:
                        warnings.append(f"Latitude maximum ({np.max(lats):.3f}) is outside requested maximum ({req_max_lat})")

            # 8. Check Depth if provided
            if "depth" in ds.coords and (expected_depth_min is not None or expected_depth_max is not None):
                depths = ds["depth"].values
                if expected_depth_min is not None and np.min(depths) < expected_depth_min - 1.0:
                    warnings.append(f"Depth minimum ({np.min(depths):.2f}m) below expected ({expected_depth_min}m)")
                if expected_depth_max is not None and np.max(depths) > expected_depth_max + 1.0:
                    warnings.append(f"Depth maximum ({np.max(depths):.2f}m) above expected ({expected_depth_max}m)")

            # 9. Validate variables
            reg_dataset: Optional[RegisteredDataset] = None
            if expected_dataset_id:
                reg_dataset = registry.get(expected_dataset_id)

            target_vars = expected_variables or list(ds.data_vars.keys())

            if not target_vars:
                errors.append("NetCDF file contains no data variables.")

            for var_name in target_vars:
                if var_name not in ds.data_vars:
                    errors.append(f"Expected variable '{var_name}' not found in NetCDF dataset.")
                    continue

                var_data = ds[var_name]
                raw_arr = var_data.values

                # Metadata & units check
                units = var_data.attrs.get("units")
                std_name = var_data.attrs.get("standard_name")

                expected_meta = reg_dataset.variable_metadata.get(var_name) if reg_dataset else None
                if expected_meta:
                    exp_units = expected_meta.get("units")
                    if exp_units and units != exp_units:
                        warnings.append(f"Variable '{var_name}' units '{units}' differ from registry units '{exp_units}'")

                # Statistical checks
                float_arr = np.asarray(raw_arr, dtype=float)
                total_pts = int(float_arr.size)
                nan_mask = np.isnan(float_arr)
                nan_count = int(np.sum(nan_mask))
                valid_mask = ~nan_mask
                valid_count = int(np.sum(valid_mask))

                v_stat = VariableStats(
                    variable_name=var_name,
                    standard_name=std_name,
                    units=units,
                    total_points=total_pts,
                    valid_points=valid_count,
                    missing_points=nan_count,
                )

                if valid_count > 0:
                    valid_vals = float_arr[valid_mask]
                    v_stat.min_value = float(np.min(valid_vals))
                    v_stat.max_value = float(np.max(valid_vals))
                    v_stat.mean_value = float(np.mean(valid_vals))
                    v_stat.std_value = float(np.std(valid_vals))

                    # Physical bounds check
                    valid_min_limit = None
                    valid_max_limit = None

                    if expected_meta:
                        valid_min_limit = expected_meta.get("valid_min")
                        valid_max_limit = expected_meta.get("valid_max")
                    elif "valid_min" in var_data.attrs and "valid_max" in var_data.attrs:
                        valid_min_limit = float(var_data.attrs["valid_min"])
                        valid_max_limit = float(var_data.attrs["valid_max"])

                    if valid_min_limit is not None and valid_max_limit is not None:
                        oob_mask = (valid_vals < valid_min_limit) | (valid_vals > valid_max_limit)
                        oob_count = int(np.sum(oob_mask))
                        v_stat.out_of_range_points = oob_count
                        if oob_count > 0:
                            warn_msg = (
                                f"Variable '{var_name}': {oob_count} points outside declared range "
                                f"[{valid_min_limit}, {valid_max_limit}] {units}"
                            )
                            v_stat.warnings.append(warn_msg)
                            warnings.append(warn_msg)
                else:
                    all_nan_msg = f"Variable '{var_name}': all points are NaN or masked (land mask / missing observation)."
                    v_stat.warnings.append(all_nan_msg)
                    warnings.append(all_nan_msg)

                var_stats[var_name] = v_stat

        finally:
            ds.close()

        # Determine overall status
        status = "passed"
        is_valid = True
        if errors:
            status = "failed"
            is_valid = False
        elif warnings:
            status = "warnings"

        return ValidationReport(
            file_path=str(path),
            status=status,
            is_valid=is_valid,
            cf_conventions=cf_conv,
            dimensions=dims_dict,
            coordinates_summary=coords_summary,
            variable_stats=var_stats,
            warnings=warnings,
            errors=errors,
        )


# Global validator instance
validator = NetCDFValidator()
