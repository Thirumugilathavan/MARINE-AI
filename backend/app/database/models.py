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
from geoalchemy2 import Geometry

# JSON type that uses JSONB on PostgreSQL and JSON on SQLite
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

# Spatial Geometry Point type: native PostGIS Geometry on PostgreSQL, Text on SQLite for test compatibility
GEOMETRY_POINT = Text().with_variant(Geometry("POINT", srid=4326), "postgresql")


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


# ==============================================================================
# PHASE 4: BIODIVERSITY & SPECIES OCCURRENCES (OBIS / GBIF)
# ==============================================================================

class MarineSpeciesOccurrenceModel(Base):
    """
    Stores marine species occurrence records from OBIS and GBIF with PostGIS spatial geometry.
    """
    __tablename__ = "marine_species_occurrences"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # 'obis' or 'gbif'
    occurrence_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    scientific_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    accepted_scientific_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    aphia_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    taxon_rank: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    kingdom: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    phylum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    class_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    order_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    family: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    genus: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    geom: Mapped[Optional[Any]] = mapped_column(GEOMETRY_POINT, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    coordinate_uncertainty_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    depth_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    event_date: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    basis_of_record: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    institution_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    dataset_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    licence: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    bibliographic_citation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    raw_record: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    is_reconciled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reconciled_cluster_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


# ==============================================================================
# PHASE 5: WORMS TAXONOMY HIERARCHY & SYNONYMS
# ==============================================================================

class MarineTaxonModel(Base):
    """
    Standardized relational taxonomy from the World Register of Marine Species (WoRMS).
    """
    __tablename__ = "marine_taxa"

    aphia_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scientific_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    authority: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    rank: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # 'accepted', 'unaccepted', 'synonym'
    valid_aphia_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    valid_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    valid_authority: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    kingdom: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    phylum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    class_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    order_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    family: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    genus: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    is_marine: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=True)
    is_brackish: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_freshwater: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_terrestrial: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_extinct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    citation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lsid: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    worms_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    raw_aphia_record: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class TaxonSynonymModel(Base):
    """
    Synonym mappings referencing official Aphia records.
    """
    __tablename__ = "taxon_synonyms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    aphia_id: Mapped[int] = mapped_column(Integer, ForeignKey("marine_taxa.aphia_id", ondelete="CASCADE"), nullable=False, index=True)
    synonym_aphia_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    synonym_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    synonym_authority: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    synonym_status: Mapped[str] = mapped_column(String(64), nullable=False, default="unaccepted")


class TaxonomyLookupCacheModel(Base):
    """
    Local cache for scientific name lookups to minimize external WoRMS API load.
    """
    __tablename__ = "taxonomy_lookup_cache"

    query_name: Mapped[str] = mapped_column(String(256), primary_key=True)
    aphia_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    match_status: Mapped[str] = mapped_column(String(64), nullable=False)  # 'exact_match', 'fuzzy_match', 'not_found'
    raw_result: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


# ==============================================================================
# PHASE 6: FAO FISHERIES & AQUACULTURE STATISTICS
# ==============================================================================

class FisheriesStatisticModel(Base):
    """
    Stores official FAO capture fisheries and aquaculture production statistics.
    """
    __tablename__ = "fisheries_statistics"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    country_iso3: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    country_name: Mapped[str] = mapped_column(String(128), nullable=False)
    fao_major_area: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # e.g. "Area 51 - Western Indian Ocean"
    species_scientific_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, index=True)
    species_common_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    species_alpha3_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True, index=True)  # FAO 3-alpha e.g. "YFT" for Yellowfin tuna
    production_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # 'capture' or 'aquaculture'
    environment: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # 'marine', 'brackish', 'inland'
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quantity_tonnes: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="tonnes")
    source_dataset: Mapped[str] = mapped_column(String(128), nullable=False, default="FAO FishStat")
    licence: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, default="FAO Open Data Policy")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


# ==============================================================================
# PHASE 7: CENTRAL SCIENTIFIC DATASET CATALOGUE
# ==============================================================================

class ScientificCatalogEntryModel(Base):
    """
    Central catalog covering all 9 integrated marine scientific data providers
    with strict 7-stage verification lifecycle tracking.
    """
    __tablename__ = "scientific_catalog_entries"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # dataset_id
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dataset_name: Mapped[str] = mapped_column(String(256), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    official_source_url: Mapped[str] = mapped_column(String(512), nullable=False)
    doi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    licence: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Text] = mapped_column(Text, nullable=False)

    variables: Mapped[List[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    variable_units: Mapped[Dict[str, str]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    spatial_coverage: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    temporal_coverage: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    spatial_resolution: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    temporal_resolution: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    depth_coverage: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    data_format: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_method: Mapped[str] = mapped_column(String(64), nullable=False)
    update_frequency: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # 7-stage lifecycle:
    # 'discovered', 'metadata_verified', 'access_tested', 'sample_validated',
    # 'production_approved', 'unavailable', 'requires_manual_action'
    verification_lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="discovered", index=True)
    quality_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    requires_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


# ==============================================================================
# PHASE 8 & 9: eDNA RESEARCH DATA WORKFLOW
# ==============================================================================

class EDNASampleModel(Base):
    """
    Environmental DNA field collection metadata linked to sequence files in SeaweedFS.
    """
    __tablename__ = "edna_samples"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    sample_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expedition_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    station_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    geom: Mapped[Optional[Any]] = mapped_column(GEOMETRY_POINT, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    collection_depth_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    water_body: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    collection_method: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # Niskin bottle, Sterivex filter, grab
    preservation_method: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # Longmire buffer, -80C freezing
    extraction_protocol: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # DNeasy Blood & Tissue
    target_gene: Mapped[str] = mapped_column(String(64), nullable=False)  # '12S', '16S', '18S', 'COI'
    primer_forward: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    primer_reverse: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    sequencing_platform: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # Illumina NovaSeq, Oxford Nanopore

    # SeaweedFS file references
    raw_fastq_forward_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    raw_fastq_reverse_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    sha256_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EDNATaxonomicAssignmentModel(Base):
    """
    Structured taxonomic matches resulting from eDNA sequence analysis with scientific interpretation safeguards.
    """
    __tablename__ = "edna_taxonomic_assignments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    sample_id: Mapped[str] = mapped_column(String(64), ForeignKey("edna_samples.id", ondelete="CASCADE"), nullable=False, index=True)
    asv_sequence_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence_header: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    read_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    matched_scientific_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    aphia_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    taxonomic_rank: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    identity_percent: Mapped[float] = mapped_column(Float, nullable=False)  # e.g. 99.5%
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0 to 1.0

    reference_database: Mapped[str] = mapped_column(String(128), nullable=False)  # 'MitoFish', 'SILVA', 'NCBI-nt', 'PR2'
    scientific_interpretation_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=False,
        default="Sequence match constitutes molecular detection only; physical organism presence requires ecological and oceanographic validation."
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


# ==============================================================================
# PHASE 10: MARINE IMAGES & UNDERWATER VIDEOS MANAGEMENT
# ==============================================================================

class MarineMediaAssetModel(Base):
    """
    Stores research media (images, ROV/AUV underwater video) persisted in the marine-media SeaweedFS bucket.
    """
    __tablename__ = "marine_media_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expedition_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    sample_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    bucket_name: Mapped[str] = mapped_column(String(64), nullable=False, default="marine-media")
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    geom: Mapped[Optional[Any]] = mapped_column(GEOMETRY_POINT, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    depth_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    camera_sensor_info: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    licence: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")  # 'active', 'archived', 'processing'
    media_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


# ==============================================================================
# PHASE 11: CTD & ADCP SCIENTIFIC OBSERVATIONS
# ==============================================================================

class OceanographicProfileModel(Base):
    """
    Profile header representing a single CTD cast or ADCP deployment.
    """
    __tablename__ = "oceanographic_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    instrument_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # 'CTD', 'ADCP'
    station_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expedition_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    geom: Mapped[Optional[Any]] = mapped_column(GEOMETRY_POINT, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    profile_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_depth_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_levels: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    raw_file_storage_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    raw_file_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    instrument_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OceanographicObservationModel(Base):
    """
    Vertical depth/pressure level observations extracted from CTD or ADCP profiles.
    """
    __tablename__ = "oceanographic_observations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id: Mapped[str] = mapped_column(String(64), ForeignKey("oceanographic_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    depth_m: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    pressure_dbar: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # CTD parameters
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    salinity_psu: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conductivity_sm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    potential_density_kgm3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ADCP current velocity parameters
    current_speed_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    velocity_u_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Eastward
    velocity_v_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Northward
    velocity_w_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Vertical

    quality_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 1=Good, 2=Probably Good, 3=Questionable, 4=Bad

