"""
Pydantic validation schemas for Copernicus Marine endpoints.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class CopernicusProductItemSchema(BaseModel):
    product_id: str = Field(..., description="Unique Copernicus Marine product identifier")
    title: str = Field(..., description="Official title of the marine product")


class CopernicusSearchResponseSchema(BaseModel):
    provider: str = Field("Copernicus Marine", description="Data provider name")
    query: str = Field(..., description="Search keyword used")
    total_found: int = Field(..., description="Total products found matching query")
    returned: int = Field(..., description="Number of products returned in this page")
    products: List[CopernicusProductItemSchema] = Field(default_factory=list, description="List of matching products")


class PreviewRequestSchema(BaseModel):
    dataset_id: str = Field(
        default="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
        description="Verified Copernicus dataset ID",
    )
    variables: List[str] = Field(
        default=["thetao"],
        description="Variables to retrieve, e.g. ['thetao']",
    )
    minimum_longitude: float = Field(
        default=85.0,
        ge=-180.0,
        le=180.0,
        description="Minimum longitude bound (-180 to 180)",
    )
    maximum_longitude: float = Field(
        default=85.2,
        ge=-180.0,
        le=180.0,
        description="Maximum longitude bound (-180 to 180)",
    )
    minimum_latitude: float = Field(
        default=12.0,
        ge=-90.0,
        le=90.0,
        description="Minimum latitude bound (-90 to 90)",
    )
    maximum_latitude: float = Field(
        default=12.2,
        ge=-90.0,
        le=90.0,
        description="Maximum latitude bound (-90 to 90)",
    )
    start_datetime: str = Field(
        default="2026-11-20",
        description="ISO 8601 start datetime string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
    )
    end_datetime: str = Field(
        default="2026-11-20",
        description="ISO 8601 end datetime string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
    )
    minimum_depth: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Shallowest depth level in meters (optional)",
    )
    maximum_depth: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Deepest depth level in meters (optional)",
    )
    dataset_version: Optional[str] = Field(
        default=None,
        description="Optional dataset version override",
    )
    dataset_part: Optional[str] = Field(
        default=None,
        description="Optional dataset part override",
    )


class IngestionRequestSchema(PreviewRequestSchema):
    output_filename: Optional[str] = Field(
        default=None,
        description="Optional clean filename for the downloaded NetCDF file",
    )
    retain_in_s3: bool = Field(
        default=False,
        description="Whether to retain a copy in SeaweedFS S3 storage",
    )


class PreviewResponseSchema(BaseModel):
    request_id: str
    dataset_id: str
    product_id: str
    product_title: str
    requested_variables: List[str]
    requested_extent: Dict[str, float]
    selected_extent: Dict[str, Any]
    time_range: Dict[str, str]
    depth_range: Dict[str, Optional[float]]
    estimated_file_size_mb: float
    estimated_data_transfer_mb: float
    dry_run_status: str
    dry_run_message: str


class IngestionJobSummarySchema(BaseModel):
    id: str
    provider: str
    dataset_id: str
    product_id: str
    status: str
    requested_variables: List[str]
    requested_spatial_extent: Dict[str, float]
    requested_time_interval: Dict[str, Any]
    requested_depth_interval: Dict[str, Any]
    error_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class IngestionJobDetailSchema(IngestionJobSummarySchema):
    assets: List[Dict[str, Any]] = []
    validation_reports: List[Dict[str, Any]] = []
    provenance_records: List[Dict[str, Any]] = []
