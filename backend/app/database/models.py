"""
SQLAlchemy 2.0 data models for the MARINE-AI Platform.

Implements entities for:
- Dataset Registry
- Ingestion Jobs
- Ingestion Assets
- Validation Reports
- Scientific Provenance Records
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import uuid

from sqlalchemy import (
    String,
    Text,
    Integer,
    BigInteger,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSON type that uses JSONB on PostgreSQL and JSON on SQLite
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DataProviderModel(Base):
    """
    Stores registered marine data providers and their operational metadata.
    """
    __tablename__ = "data_providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # provider_id e.g. "copernicus", "noaa", "argo", "incois"
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    organization: Mapped[str] = mapped_column(String(256), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    documentation_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    access_method: Mapped[str] = mapped_column(String(64), nullable=False)
    authentication_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="operational")
    supported_formats: Mapped[List[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    rate_limits_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    licence_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class DatasetRegistryModel(Base):
    """
    Stores verified provider dataset definitions and metadata.
    """
    __tablename__ = "dataset_registry"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # dataset_id
    provider: Mapped[str] = mapped_column(String(100), nullable=False, default="Copernicus Marine Service")
    product_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    dataset_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_part: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, default="default")
    product_title: Mapped[str] = mapped_column(String(256), nullable=False)
    dataset_description: Mapped[str] = mapped_column(Text, nullable=False)
    available_variables: Mapped[List[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    variable_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    temporal_resolution: Mapped[str] = mapped_column(String(64), nullable=False)
    spatial_resolution: Mapped[str] = mapped_column(String(64), nullable=False)
    data_type: Mapped[str] = mapped_column(String(100), nullable=False, default="model_analysis_forecast")
    spatial_coverage: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    depth_levels_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    depth_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    depth_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_documentation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    licence_information: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="verified")
    last_metadata_verification_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class IngestionJobModel(Base):
    """
    Tracks state transitions and metadata for asynchronous or synchronous ingestion jobs.
    """
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String(100), nullable=False, default="Copernicus Marine Service")
    product_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    dataset_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_part: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    requested_variables: Mapped[List[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    requested_spatial_extent: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    requested_time_interval: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    requested_depth_interval: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    request_parameters: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    # Relationships
    assets: Mapped[List["IngestionAssetModel"]] = relationship("IngestionAssetModel", back_populates="job", cascade="all, delete-orphan")
    validation_reports: Mapped[List["ValidationReportModel"]] = relationship("ValidationReportModel", back_populates="job", cascade="all, delete-orphan")
    provenance_records: Mapped[List["ProvenanceRecordModel"]] = relationship("ProvenanceRecordModel", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_ingestion_jobs_status_created", "status", "created_at"),
    )


class IngestionAssetModel(Base):
    """
    Represents a downloaded or stored binary asset (e.g. NetCDF file).
    """
    __tablename__ = "ingestion_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    file_format: Mapped[str] = mapped_column(String(64), nullable=False, default="NetCDF-4")
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False, default="local_staging")  # "local_staging" or "seaweedfs_s3"
    storage_bucket: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    storage_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    local_staging_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # "pending", "passed", "warnings", "failed"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    job: Mapped["IngestionJobModel"] = relationship("IngestionJobModel", back_populates="assets")
    validation_reports: Mapped[List["ValidationReportModel"]] = relationship("ValidationReportModel", back_populates="asset")


class ValidationReportModel(Base):
    """
    Stores structured validation metrics and reports for scientific data files.
    """
    __tablename__ = "validation_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("ingestion_assets.id", ondelete="SET NULL"), nullable=True, index=True)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="passed")  # "passed", "warnings", "failed"
    variables_validated: Mapped[List[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    dimensions: Mapped[Dict[str, int]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    coordinates_summary: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    valid_points_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    missing_points_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    invalid_points_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    statistics: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)  # min, max, mean, std
    cf_conventions: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    warnings: Mapped[List[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    errors: Mapped[List[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    job: Mapped["IngestionJobModel"] = relationship("IngestionJobModel", back_populates="validation_reports")
    asset: Mapped[Optional["IngestionAssetModel"]] = relationship("IngestionAssetModel", back_populates="validation_reports")


class ProvenanceRecordModel(Base):
    """
    Full lineage and provenance tracking for retrieved marine observations and model outputs.
    """
    __tablename__ = "provenance_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, default="Copernicus Marine Service")
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    dataset_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_part: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider_doi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieval_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    requested_date_range: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    actual_data_date_range: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    spatial_extent: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    variables: Mapped[List[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    units: Mapped[Dict[str, str]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    processing_method: Mapped[str] = mapped_column(String(128), nullable=False, default="copernicusmarine_subset_api")
    source_licence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    toolbox_version: Mapped[str] = mapped_column(String(32), nullable=False, default="2.5.1")
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    validation_report_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Relationships
    job: Mapped["IngestionJobModel"] = relationship("IngestionJobModel", back_populates="provenance_records")
