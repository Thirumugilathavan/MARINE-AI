"""
Copernicus Marine Service core orchestrator.

Preserves catalogue search and orchestrates dataset registry, preview/dry-run,
bounded retrieval, NetCDF validation, S3 retention policy, and PostgreSQL persistence.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import uuid

import copernicusmarine
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.core.config import settings
from app.database.models import (
    DatasetRegistryModel,
    IngestionJobModel,
    IngestionAssetModel,
    ValidationReportModel,
    ProvenanceRecordModel,
)
from app.storage.s3_client import s3_client
from app.modules.data_sources.copernicus.dataset_registry import (
    registry,
    RegisteredDataset,
)
from app.modules.data_sources.copernicus.retrieval import (
    retrieval_service,
    RetrievalParameters,
    PreviewResponse,
)
from app.modules.data_sources.copernicus.validation import (
    validator,
    ValidationReport,
)
from app.modules.data_sources.copernicus.metadata import (
    compute_sha256,
    build_provenance_record,
)
from app.modules.data_sources.copernicus.exceptions import (
    CopernicusError,
    DatasetNotFoundError,
    RetrievalError,
    ValidationError,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# Existing Catalogue Functionality (PRESERVED)
# ==============================================================================
def search_catalogue(keyword: str, limit: int = 10) -> Dict[str, Any]:
    """
    Search the Copernicus Marine catalogue.

    Args:
        keyword: Search term, such as thetao, salinity, or chlorophyll.
        limit: Maximum number of products to return.

    Returns:
        A list of catalogue products.
    """
    result = copernicusmarine.describe(
        contains=[keyword],
        disable_progress_bar=True,
    )

    products = []
    for product in result.products[:limit]:
        products.append(
            {
                "product_id": product.product_id,
                "title": product.title,
            }
        )

    return {
        "provider": "Copernicus Marine",
        "query": keyword,
        "total_found": len(result.products),
        "returned": len(products),
        "products": products,
    }


# ==============================================================================
# Dataset Registry Service Functions
# ==============================================================================
def list_registered_datasets() -> List[Dict[str, Any]]:
    """Lists all verified and registered Copernicus datasets."""
    return [ds.to_dict() for ds in registry.list_all()]


def get_registered_dataset(dataset_id: str) -> Dict[str, Any]:
    """Retrieves metadata for one registered Copernicus dataset."""
    return registry.get_or_raise(dataset_id).to_dict()


# ==============================================================================
# Ingestion Workflow Operations
# ==============================================================================
def preview_ingestion(params: RetrievalParameters) -> Dict[str, Any]:
    """
    Executes a dry-run subset query to validate parameters and estimate file size.
    Never downloads binary data.
    """
    request_id = str(uuid.uuid4())
    preview_res = retrieval_service.preview(params, request_id)
    return preview_res.to_dict()


def create_ingestion_job(
    params: RetrievalParameters,
    db: Optional[Session] = None,
    retain_in_s3: bool = False,
) -> IngestionJobModel:
    """
    Validates request and registers an IngestionJob record in the database.
    """
    dataset = retrieval_service.validate_parameters(params)

    job = IngestionJobModel(
        id=str(uuid.uuid4()),
        provider=dataset.provider,
        product_id=dataset.product_id,
        dataset_id=dataset.dataset_id,
        dataset_version=params.dataset_version or dataset.dataset_version,
        dataset_part=params.dataset_part or dataset.dataset_part,
        requested_variables=params.variables,
        requested_spatial_extent={
            "minimum_longitude": params.minimum_longitude,
            "maximum_longitude": params.maximum_longitude,
            "minimum_latitude": params.minimum_latitude,
            "maximum_latitude": params.maximum_latitude,
        },
        requested_time_interval={
            "start": params.start_datetime,
            "end": params.end_datetime,
        },
        requested_depth_interval={
            "minimum_depth": params.minimum_depth,
            "maximum_depth": params.maximum_depth,
        },
        request_parameters={
            "output_filename": params.output_filename,
            "retain_in_s3": retain_in_s3,
        },
        status="queued",
        created_at=datetime.now(timezone.utc),
    )

    if db:
        db.add(job)
        db.commit()
        db.refresh(job)

    return job


def process_ingestion_job(
    job_id: str,
    params: RetrievalParameters,
    db: Optional[Session] = None,
    retain_in_s3: bool = False,
) -> Dict[str, Any]:
    """
    Executes the full ingestion pipeline:
    1. Retrieval via copernicusmarine.subset()
    2. NetCDF validation using xarray
    3. Provenance record generation
    4. Optional SeaweedFS S3 storage policy retention
    5. Database state persistence
    """
    job: Optional[IngestionJobModel] = None
    if db:
        job = db.get(IngestionJobModel, job_id)
        if job:
            job.status = "downloading"
            job.started_at = datetime.now(timezone.utc)
            db.commit()

    try:
        # Step 1: Retrieval
        downloaded_file = retrieval_service.execute_retrieval(
            params=params,
            job_id=job_id,
            custom_output_filename=params.output_filename,
        )

        if db and job:
            job.status = "validating_data"
            db.commit()

        # Step 2: NetCDF Validation
        val_report: ValidationReport = validator.validate_file(
            file_path=downloaded_file,
            expected_dataset_id=params.dataset_id,
            expected_variables=params.variables,
            expected_bounds={
                "minimum_longitude": params.minimum_longitude,
                "maximum_longitude": params.maximum_longitude,
                "minimum_latitude": params.minimum_latitude,
                "maximum_latitude": params.maximum_latitude,
            },
            expected_start_time=params.start_datetime,
            expected_end_time=params.end_datetime,
            expected_depth_min=params.minimum_depth,
            expected_depth_max=params.maximum_depth,
        )

        checksum = compute_sha256(downloaded_file)
        file_size = downloaded_file.stat().st_size

        # Step 3: Asset Record
        asset = IngestionAssetModel(
            id=str(uuid.uuid4()),
            job_id=job_id,
            filename=downloaded_file.name,
            file_format="NetCDF-4",
            file_size_bytes=file_size,
            sha256_checksum=checksum,
            storage_backend="local_staging",
            local_staging_path=str(downloaded_file),
            validation_status=val_report.status,
            created_at=datetime.now(timezone.utc),
        )

        # Step 4: Storage Retention Policy (SeaweedFS S3)
        # Default policy: API-accessible data stays in staging unless retention explicitly requested.
        if retain_in_s3:
            s3_key = f"copernicus/{params.dataset_id}/{job_id}/{downloaded_file.name}"
            try:
                s3_client.upload_file(
                    str(downloaded_file),
                    settings.seaweedfs_bucket_raw,
                    s3_key,
                )
                asset.storage_backend = "seaweedfs_s3"
                asset.storage_bucket = settings.seaweedfs_bucket_raw
                asset.storage_key = s3_key
                logger.info(f"[Job {job_id}] Stored in SeaweedFS S3 bucket '{settings.seaweedfs_bucket_raw}' key '{s3_key}'")
            except Exception as s3_err:
                logger.warning(f"[Job {job_id}] S3 upload deferred (kept local): {s3_err}")

        # Step 5: Validation Report Model
        # Format variable stats dictionary
        v_stats_dict = {
            vname: {
                "standard_name": vs.standard_name,
                "units": vs.units,
                "total_points": vs.total_points,
                "valid_points": vs.valid_points,
                "missing_points": vs.missing_points,
                "out_of_range_points": vs.out_of_range_points,
                "min": vs.min_value,
                "max": vs.max_value,
                "mean": vs.mean_value,
                "std": vs.std_value,
                "warnings": vs.warnings,
            }
            for vname, vs in val_report.variable_stats.items()
        }

        report_record = ValidationReportModel(
            id=str(uuid.uuid4()),
            job_id=job_id,
            asset_id=asset.id,
            validation_status=val_report.status,
            variables_validated=params.variables,
            dimensions=val_report.dimensions,
            coordinates_summary=val_report.coordinates_summary,
            valid_points_count=sum(vs.valid_points for vs in val_report.variable_stats.values()),
            missing_points_count=sum(vs.missing_points for vs in val_report.variable_stats.values()),
            invalid_points_count=sum(vs.out_of_range_points for vs in val_report.variable_stats.values()),
            statistics=v_stats_dict,
            cf_conventions=val_report.cf_conventions,
            warnings=val_report.warnings,
            errors=val_report.errors,
            created_at=datetime.now(timezone.utc),
        )

        # Step 6: Provenance Record
        dataset = registry.get_or_raise(params.dataset_id)
        prov_dict = build_provenance_record(
            job_id=job_id,
            dataset_id=params.dataset_id,
            product_id=dataset.product_id,
            requested_variables=params.variables,
            requested_spatial_extent={
                "minimum_longitude": params.minimum_longitude,
                "maximum_longitude": params.maximum_longitude,
                "minimum_latitude": params.minimum_latitude,
                "maximum_latitude": params.maximum_latitude,
            },
            requested_time_interval={
                "start": params.start_datetime,
                "end": params.end_datetime,
            },
            file_path=downloaded_file,
            validation_report_id=report_record.id,
            dataset_version=dataset.dataset_version,
            dataset_part=dataset.dataset_part,
        )

        prov_record = ProvenanceRecordModel(
            id=str(uuid.uuid4()),
            job_id=job_id,
            provider=prov_dict["provider"],
            product_id=prov_dict["product_id"],
            dataset_id=prov_dict["dataset_id"],
            dataset_version=prov_dict["dataset_version"],
            dataset_part=prov_dict["dataset_part"],
            retrieval_timestamp=datetime.fromisoformat(prov_dict["retrieval_timestamp"]),
            requested_date_range=prov_dict["requested_date_range"],
            actual_data_date_range=prov_dict["actual_data_date_range"],
            spatial_extent=prov_dict["spatial_extent"],
            variables=prov_dict["variables"],
            units=prov_dict["units"],
            processing_method=prov_dict["processing_method"],
            source_licence=prov_dict["source_licence"],
            toolbox_version=prov_dict["toolbox_version"],
            sha256_checksum=prov_dict["sha256_checksum"],
            validation_report_id=report_record.id,
            created_at=datetime.now(timezone.utc),
        )

        # Step 7: Finalize Database State
        if db and job:
            db.add(asset)
            db.add(report_record)
            db.add(prov_record)

            if val_report.is_valid:
                job.status = "completed"
            else:
                job.status = "failed"
                job.error_summary = "; ".join(val_report.errors)

            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(job)

        return {
            "job_id": job_id,
            "status": "completed" if val_report.is_valid else "failed",
            "dataset_id": params.dataset_id,
            "file_path": str(downloaded_file),
            "file_size_bytes": file_size,
            "sha256_checksum": checksum,
            "storage_backend": asset.storage_backend,
            "storage_bucket": asset.storage_bucket,
            "storage_key": asset.storage_key,
            "validation_report": val_report.to_dict(),
            "provenance": prov_dict,
        }

    except Exception as exc:
        logger.error(f"[Job {job_id}] Pipeline execution failed: {exc}", exc_info=True)
        if db and job:
            job.status = "failed"
            job.error_summary = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise


def get_job(db: Session, job_id: str) -> Optional[IngestionJobModel]:
    """Retrieves an IngestionJob by ID."""
    return db.get(IngestionJobModel, job_id)


def list_jobs(db: Session, limit: int = 50, status: Optional[str] = None) -> List[IngestionJobModel]:
    """Lists recent ingestion jobs."""
    stmt = select(IngestionJobModel).order_by(desc(IngestionJobModel.created_at)).limit(limit)
    if status:
        stmt = stmt.where(IngestionJobModel.status == status)
    return list(db.scalars(stmt).all())
