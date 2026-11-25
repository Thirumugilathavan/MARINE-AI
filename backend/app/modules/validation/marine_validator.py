"""
Marine data validation module.

Provides spatial bounds validation, parameter checks, physical sanity range verification,
and data quality indicators for oceanographic observations.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import numpy as np

from app.modules.data_sources.copernicus.constants import (
    DEFAULT_INDIAN_OCEAN_BOUNDS,
    SUPPORTED_VARIABLES,
    CADENCE_DATASET_MAP,
)


@dataclass
class BoundingBox:
    minimum_longitude: float
    maximum_longitude: float
    minimum_latitude: float
    maximum_latitude: float

    def validate(self) -> None:
        if not (-180.0 <= self.minimum_longitude <= 180.0):
            raise ValueError(f"minimum_longitude {self.minimum_longitude} out of bounds [-180, 180]")
        if not (-180.0 <= self.maximum_longitude <= 180.0):
            raise ValueError(f"maximum_longitude {self.maximum_longitude} out of bounds [-180, 180]")
        if not (-90.0 <= self.minimum_latitude <= 90.0):
            raise ValueError(f"minimum_latitude {self.minimum_latitude} out of bounds [-90, 90]")
        if not (-90.0 <= self.maximum_latitude <= 90.0):
            raise ValueError(f"maximum_latitude {self.maximum_latitude} out of bounds [-90, 90]")
        if self.minimum_longitude > self.maximum_longitude:
            raise ValueError(
                f"minimum_longitude ({self.minimum_longitude}) must be <= maximum_longitude ({self.maximum_longitude})"
            )
        if self.minimum_latitude > self.maximum_latitude:
            raise ValueError(
                f"minimum_latitude ({self.minimum_latitude}) must be <= maximum_latitude ({self.maximum_latitude})"
            )

    @classmethod
    def default_indian_ocean(cls) -> "BoundingBox":
        return cls(**DEFAULT_INDIAN_OCEAN_BOUNDS)


@dataclass
class VariableValidationResult:
    variable: str
    total_points: int = 0
    valid_points: int = 0
    nan_points: int = 0
    out_of_bounds_points: int = 0
    min_observed: Optional[float] = None
    max_observed: Optional[float] = None
    mean_observed: Optional[float] = None
    is_valid: bool = True
    warnings: List[str] = field(default_factory=list)


@dataclass
class MarineValidationReport:
    is_valid: bool
    cadence: str
    variables: List[str]
    bounding_box: Dict[str, float]
    variable_reports: Dict[str, VariableValidationResult] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    quality_score: float = 1.0


def validate_cadence(cadence: str) -> None:
    if cadence not in CADENCE_DATASET_MAP:
        valid = list(CADENCE_DATASET_MAP.keys())
        raise ValueError(f"Unsupported cadence '{cadence}'. Must be one of {valid}")


def validate_variables(variables: List[str]) -> None:
    if not variables:
        raise ValueError("At least one oceanographic variable must be specified.")
    for var in variables:
        if var not in SUPPORTED_VARIABLES:
            valid = list(SUPPORTED_VARIABLES.keys())
            raise ValueError(f"Unsupported variable '{var}'. Must be one of {valid}")


def validate_bounding_box(
    min_lon: float,
    max_lon: float,
    min_lat: float,
    max_lat: float,
) -> BoundingBox:
    bbox = BoundingBox(
        minimum_longitude=min_lon,
        maximum_longitude=max_lon,
        minimum_latitude=min_lat,
        maximum_latitude=max_lat,
    )
    bbox.validate()
    return bbox


def validate_ocean_array(variable: str, data: np.ndarray) -> VariableValidationResult:
    """
    Validates a numpy array of oceanographic measurements against physical limits.
    """
    if variable not in SUPPORTED_VARIABLES:
        raise ValueError(f"Unknown variable '{variable}'")

    meta = SUPPORTED_VARIABLES[variable]
    min_phys = meta["min_valid_physical"]
    max_phys = meta["max_valid_physical"]

    arr = np.asarray(data, dtype=float)
    total_points = int(arr.size)
    nan_mask = np.isnan(arr)
    nan_points = int(np.sum(nan_mask))
    valid_mask = ~nan_mask
    valid_points = int(np.sum(valid_mask))

    result = VariableValidationResult(
        variable=variable,
        total_points=total_points,
        valid_points=valid_points,
        nan_points=nan_points,
    )

    if valid_points > 0:
        valid_values = arr[valid_mask]
        result.min_observed = float(np.min(valid_values))
        result.max_observed = float(np.max(valid_values))
        result.mean_observed = float(np.mean(valid_values))

        out_of_bounds = (valid_values < min_phys) | (valid_values > max_phys)
        oob_count = int(np.sum(out_of_bounds))
        result.out_of_bounds_points = oob_count

        if oob_count > 0:
            result.is_valid = False
            result.warnings.append(
                f"{oob_count} values outside physical range [{min_phys}, {max_phys}] {meta['units']}"
            )
    else:
        result.is_valid = False
        result.warnings.append("All points are NaN (land mask or missing data).")

    return result
