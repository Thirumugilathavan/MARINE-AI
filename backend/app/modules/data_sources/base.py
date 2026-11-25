"""
Base classes, interfaces, and data structures for the Unified Marine Data Provider Architecture.

Defines the contract that every marine data provider (Copernicus, NOAA, Argo, INCOIS)
must fulfill, ensuring uniform catalogue discovery, validation, retrieval,
provenance tracking, and persistence.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Union


@dataclass
class ProviderMetadata:
    """Metadata describing a marine data provider and its access capabilities."""
    provider_id: str
    name: str
    organization: str
    base_url: str
    documentation_url: str
    access_method: str  # e.g., "toolbox", "erddap_griddap", "erddap_tabledap", "gdac_https"
    authentication_required: bool
    auth_description: str
    status: str = "active"  # "active", "operational", "maintenance", "blocked"
    supported_formats: List[str] = field(default_factory=lambda: ["NetCDF-4", "NetCDF-3", "JSON", "CSV"])
    rate_limits_info: str = "Standard institutional fair use"
    licence_info: str = "Open Access / Scientific Research License"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderDatasetMeta:
    """Standardized metadata for a dataset registered under a provider."""
    provider_id: str
    dataset_id: str
    product_id: str
    product_title: str
    dataset_description: str
    available_variables: List[str]
    variable_metadata: Dict[str, Dict[str, Any]]
    temporal_resolution: str
    spatial_resolution: str
    data_type: str  # "model_analysis_forecast", "satellite_observation", "in_situ_profile", "reanalysis"
    spatial_coverage: Dict[str, float]
    depth_levels_count: Optional[int] = None
    depth_min: Optional[float] = None
    depth_max: Optional[float] = None
    time_coverage_start: Optional[str] = None
    time_coverage_end: Optional[str] = None
    source_documentation: Optional[str] = None
    licence_information: Optional[str] = None
    verification_status: str = "verified"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnifiedRetrievalParams:
    """Standardized parameters for bounded retrieval across all providers."""
    provider_id: str
    dataset_id: str
    variables: List[str]
    minimum_longitude: float
    maximum_longitude: float
    minimum_latitude: float
    maximum_latitude: float
    start_datetime: str
    end_datetime: str
    minimum_depth: Optional[float] = None
    maximum_depth: Optional[float] = None
    dataset_version: Optional[str] = None
    dataset_part: Optional[str] = None
    output_filename: Optional[str] = None
    preferred_format: str = "netcdf"  # "netcdf", "json", "csv"
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnifiedPreviewResult:
    """Result of a dry-run/preview request."""
    request_id: str
    provider_id: str
    dataset_id: str
    estimated_size_mb: float
    estimated_total_points: Optional[int]
    bounding_box_area_deg2: float
    duration_days: float
    status: str  # "success", "valid", "warning", "error"
    message: str
    selected_extent: Dict[str, Any] = field(default_factory=dict)
    variables: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnifiedRetrievalResult:
    """Result of a data retrieval operation."""
    job_id: str
    provider_id: str
    dataset_id: str
    file_path: Path
    file_format: str
    file_size_bytes: int
    sha256_checksum: str
    retrieval_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["file_path"] = str(self.file_path)
        res["retrieval_timestamp"] = self.retrieval_timestamp.isoformat()
        return res


@dataclass
class VariableStatsSummary:
    """Summary statistics for one variable."""
    variable_name: str
    standard_name: Optional[str] = None
    units: Optional[str] = None
    total_points: int = 0
    valid_points: int = 0
    missing_points: int = 0
    out_of_range_points: int = 0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    std_value: Optional[float] = None
    qc_flag_counts: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnifiedValidationResult:
    """Standardized validation output for any provider's data asset."""
    file_path: str
    provider_id: str
    dataset_id: str
    status: str  # "passed", "warnings", "failed"
    is_valid: bool
    dimensions: Dict[str, int] = field(default_factory=dict)
    coordinates_summary: Dict[str, Any] = field(default_factory=dict)
    variable_stats: Dict[str, VariableStatsSummary] = field(default_factory=dict)
    cf_conventions: Optional[str] = None
    qc_summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    # Compatibility & extended fields
    variable_statistics: Optional[Dict[str, VariableStatsSummary]] = None
    spatial_extent: Optional[Dict[str, Any]] = None
    temporal_extent: Optional[Dict[str, Any]] = None
    file_size_bytes: Optional[int] = None
    sha256_checksum: Optional[str] = None
    spatial_bounds_valid: bool = True
    temporal_bounds_valid: bool = True
    coordinates_valid: bool = True
    variables_valid: bool = True
    actual_dimensions: Optional[Dict[str, int]] = None
    detected_variables: Optional[List[str]] = None
    additional_metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.variable_statistics and not self.variable_stats:
            self.variable_stats = self.variable_statistics
        elif self.variable_stats and not self.variable_statistics:
            self.variable_statistics = self.variable_stats
        if self.actual_dimensions and not self.dimensions:
            self.dimensions = self.actual_dimensions

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["variable_stats"] = {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in self.variable_stats.items()}
        if self.variable_statistics:
            res["variable_statistics"] = res["variable_stats"]
        return res


@dataclass
class UnifiedProvenanceInfo:
    """Standardized scientific provenance information."""
    job_id: str
    provider: str = "Unknown Provider"
    product_id: str = "Unknown Product"
    dataset_id: str = "Unknown Dataset"
    dataset_version: Optional[str] = None
    retrieval_timestamp: str = ""
    requested_date_range: Dict[str, Any] = field(default_factory=dict)
    actual_data_date_range: Dict[str, Any] = field(default_factory=dict)
    spatial_extent: Dict[str, Any] = field(default_factory=dict)
    variables: List[str] = field(default_factory=list)
    units: Dict[str, str] = field(default_factory=dict)
    processing_method: str = "unified_retrieval_service"
    source_licence: Optional[str] = None
    toolbox_version: str = "1.0"
    sha256_checksum: str = ""
    validation_report_id: Optional[str] = None
    # Compatibility fields
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    provider_url: Optional[str] = None
    dataset_title: Optional[str] = None
    source_file_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    retrieval_parameters: Optional[Dict[str, Any]] = None
    validation_status: Optional[str] = None
    licence_information: Optional[str] = None
    citation: Optional[str] = None
    provider_doi: Optional[str] = None
    additional_provenance: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.provider_name and self.provider == "Unknown Provider":
            self.provider = self.provider_name
        elif self.provider and not self.provider_name:
            self.provider_name = self.provider
        if self.licence_information and not self.source_licence:
            self.source_licence = self.licence_information
        if self.provider_doi and not self.citation:
            self.citation = self.provider_doi
        elif self.citation and not self.provider_doi:
            self.provider_doi = self.citation

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseMarineProvider(ABC):
    """
    Abstract base class for all marine data providers.
    
    Subclasses implement provider-specific protocols (Copernicus Marine Toolbox,
    ERDDAP griddap/tabledap, Argo GDAC HTTPS) while exposing a uniform API.
    """

    @abstractmethod
    def metadata(self) -> ProviderMetadata:
        """Returns provider metadata, configuration, and capabilities."""
        pass

    @property
    def provider_id(self) -> str:
        return self.metadata().provider_id

    @abstractmethod
    def list_datasets(self) -> List[ProviderDatasetMeta]:
        """Returns all verified and registered datasets for this provider."""
        pass

    @abstractmethod
    def get_dataset(self, dataset_id: str) -> ProviderDatasetMeta:
        """Returns details for a registered dataset, or raises KeyError/DatasetNotFoundError."""
        pass

    @abstractmethod
    def search_catalogue(self, keyword: str, limit: int = 10) -> Dict[str, Any]:
        """Queries the live provider catalogue for matching products/datasets."""
        pass

    @abstractmethod
    def validate_parameters(self, params: UnifiedRetrievalParams) -> None:
        """Validates spatial bounds, variable availability, and safety constraints."""
        pass

    @abstractmethod
    def preview(self, params: UnifiedRetrievalParams, request_id: Optional[str] = None) -> UnifiedPreviewResult:
        """Performs a dry-run estimation of download size and coordinate extents."""
        pass

    @abstractmethod
    def retrieve(
        self,
        params: UnifiedRetrievalParams,
        job_id: str,
        staging_dir: Path,
    ) -> UnifiedRetrievalResult:
        """Executes bounded data retrieval and saves to staging_dir / job_id."""
        pass

    @abstractmethod
    def validate_data(
        self,
        file_path: Path,
        params: UnifiedRetrievalParams,
    ) -> UnifiedValidationResult:
        """Executes scientific and structural validation on the retrieved asset."""
        pass

    @abstractmethod
    def generate_provenance(
        self,
        job_id: str,
        retrieval_result: UnifiedRetrievalResult,
        validation_result: UnifiedValidationResult,
        params: UnifiedRetrievalParams,
    ) -> UnifiedProvenanceInfo:
        """Constructs standardized scientific provenance record."""
        pass
