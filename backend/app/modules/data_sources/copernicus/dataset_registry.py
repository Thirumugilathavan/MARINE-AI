"""
Copernicus Marine Dataset Registry.

Manages verified dataset definitions, metadata, variables, spatial/temporal coverage,
and provides safe extension mechanisms for future datasets.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
)


@dataclass
class RegisteredVariable:
    short_name: str
    standard_name: str
    units: str
    long_name: str
    valid_min: Optional[float] = None
    valid_max: Optional[float] = None
    data_type: str = "float32"


@dataclass
class RegisteredDataset:
    provider: str
    product_id: str
    dataset_id: str
    dataset_version: Optional[str]
    dataset_part: Optional[str]
    product_title: str
    dataset_description: str
    available_variables: List[str]
    variable_metadata: Dict[str, Dict[str, Any]]
    temporal_resolution: str
    spatial_resolution: str
    data_type: str  # e.g. "model_analysis_forecast", "reanalysis", "in_situ"
    spatial_coverage: Dict[str, float]
    depth_levels_count: Optional[int]
    depth_min: Optional[float]
    depth_max: Optional[float]
    source_documentation: Optional[str]
    licence_information: Optional[str]
    verification_status: str
    last_metadata_verification_time: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==============================================================================
# Verified Primary Temperature Dataset Definition
# ==============================================================================
VERIFIED_TEMPERATURE_DATASET = RegisteredDataset(
    provider="Copernicus Marine Service",
    product_id="GLOBAL_ANALYSISFORECAST_PHY_001_024",
    dataset_id="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
    dataset_version="202406",
    dataset_part="default",
    product_title="Global Ocean Physics Analysis and Forecast",
    dataset_description="daily mean fields from Global Ocean Physics Analysis and Forecast updated Daily",
    available_variables=["thetao"],
    variable_metadata={
        "thetao": {
            "short_name": "thetao",
            "standard_name": "sea_water_potential_temperature",
            "long_name": "Temperature",
            "units": "degrees_C",
            "valid_min": -10.0,
            "valid_max": 40.0,
            "data_type": "float32",
            "cell_methods": "area: mean",
        }
    },
    temporal_resolution="P1D (Daily mean)",
    spatial_resolution="0.083 deg (~1/12 degree)",
    data_type="model_analysis_forecast",
    spatial_coverage={
        "minimum_longitude": -180.0,
        "maximum_longitude": 179.9167,
        "minimum_latitude": -80.0,
        "maximum_latitude": 90.0,
    },
    depth_levels_count=50,
    depth_min=0.494025,
    depth_max=5727.917,
    source_documentation="https://catalogue.marine.copernicus.eu/documents/PUM/CMEMS-GLO-PUM-001-024.pdf",
    licence_information="http://marine.copernicus.eu/services-portfolio/service-commitments-and-licence/",
    verification_status="verified",
    last_metadata_verification_time="2026-11-24T00:00:00Z",
)


class DatasetRegistry:
    """
    In-memory registry of verified Copernicus Marine datasets.
    Can be safely extended with additional verified datasets.
    """

    def __init__(self):
        self._registry: Dict[str, RegisteredDataset] = {}
        # Initially register only the verified temperature dataset
        self.register(VERIFIED_TEMPERATURE_DATASET)

    def register(self, dataset: RegisteredDataset) -> None:
        """Safely register or update a verified dataset."""
        self._registry[dataset.dataset_id] = dataset

    def get(self, dataset_id: str) -> Optional[RegisteredDataset]:
        """Retrieve a registered dataset by ID."""
        return self._registry.get(dataset_id)

    def get_or_raise(self, dataset_id: str) -> RegisteredDataset:
        """Retrieve a registered dataset by ID or raise DatasetNotFoundError."""
        ds = self._registry.get(dataset_id)
        if not ds:
            raise DatasetNotFoundError(
                f"Dataset '{dataset_id}' is not in the verified dataset registry. "
                f"Available registered datasets: {list(self._registry.keys())}"
            )
        return ds

    def list_all(self) -> List[RegisteredDataset]:
        """List all currently registered datasets."""
        return list(self._registry.values())

    def validate_variables(self, dataset_id: str, requested_variables: List[str]) -> None:
        """
        Validates that requested variables exist and are registered for the dataset.
        """
        dataset = self.get_or_raise(dataset_id)
        if not requested_variables:
            raise InvalidVariableError("At least one variable must be requested.")

        invalid_vars = [v for v in requested_variables if v not in dataset.available_variables]
        if invalid_vars:
            raise InvalidVariableError(
                f"Variables {invalid_vars} are not available in registered dataset '{dataset_id}'. "
                f"Allowed variables: {dataset.available_variables}"
            )


# Global singleton instance of the registry
registry = DatasetRegistry()
