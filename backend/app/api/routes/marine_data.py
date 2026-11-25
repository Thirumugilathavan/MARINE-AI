"""
API routes for Marine Data Sources, including Copernicus Marine catalogue discovery,
registered dataset metadata, preview (dry-run), ingestion execution, and validation.
"""

import logging
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import (
    IngestionJobModel,
    IngestionAssetModel,
    ValidationReportModel,
    ProvenanceRecordModel,
)
from app.modules.data_sources.copernicus.dataset_registry import registry
from app.modules.data_sources.copernicus.retrieval import RetrievalParameters
from app.modules.data_sources.copernicus.service import (
    search_catalogue,
    list_registered_datasets,
    get_registered_dataset,
    preview_ingestion,
    create_ingestion_job,
    process_ingestion_job,
    get_job,
    list_jobs,
)
from app.modules.data_sources.copernicus.validation import validator
from app.modules.data_sources.copernicus.schemas import (
    PreviewRequestSchema,
    PreviewResponseSchema,
    IngestionRequestSchema,
    IngestionJobSummarySchema,
    IngestionJobDetailSchema,
)
from app.modules.data_sources.copernicus.exceptions import (
    CopernicusError,
    DatasetNotFoundError,
    InvalidVariableError,
    InvalidBoundsError,
    RetrievalError,
    ValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/data-sources",
    tags=["Marine Data Sources"],
)

# In-memory job cache for fallback / test environments when DB is not running
_IN_MEMORY_JOBS: Dict[str, Dict[str, Any]] = {}


# ==============================================================================
# 1. Copernicus Catalogue Discovery (PRESERVED)
# ==============================================================================
@router.get("/copernicus/search")
def search_copernicus(
    keyword: str = Query(
        ...,
        min_length=2,
        description="Catalogue search term, e.g. thetao, salinity, chlorophyll",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Maximum number of products to return",
    ),
):
    try:
        return search_catalogue(keyword=keyword, limit=limit)

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Copernicus Marine catalogue request failed: {str(exc)}",
        ) from exc


# ==============================================================================
# 2. Registered & Verified Datasets
# ==============================================================================
@router.get("/copernicus/datasets")
def list_datasets() -> List[Dict[str, Any]]:
    """Lists all verified and registered Copernicus datasets."""
    return list_registered_datasets()


@router.get("/copernicus/datasets/{dataset_id}")
def get_dataset_details(dataset_id: str) -> Dict[str, Any]:
    """Returns metadata, coverage, depth, and variables for one registered dataset."""
    try:
        return get_registered_dataset(dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ==============================================================================
# 3. Preview (Dry-Run Subsetting)
# ==============================================================================
@router.post("/copernicus/preview", response_model=PreviewResponseSchema)
def preview_subset(request: PreviewRequestSchema):
    """
    Validates parameters and runs a Copernicus dry-run query.
    Returns estimated file size, transfer size, and selected coordinate bounds.
    Never downloads binary data.
    """
    params = RetrievalParameters(
        dataset_id=request.dataset_id,
        variables=request.variables,
        minimum_longitude=request.minimum_longitude,
        maximum_longitude=request.maximum_longitude,
        minimum_latitude=request.minimum_latitude,
        maximum_latitude=request.maximum_latitude,
        start_datetime=request.start_datetime,
        end_datetime=request.end_datetime,
        minimum_depth=request.minimum_depth,
        maximum_depth=request.maximum_depth,
        dataset_version=request.dataset_version,
        dataset_part=request.dataset_part,
    )

    try:
        return preview_ingestion(params)
    except (DatasetNotFoundError, InvalidVariableError, InvalidBoundsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RetrievalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview failed: {exc}") from exc


# ==============================================================================
# 4. Ingestion Job Execution & Status
# ==============================================================================
def _run_ingestion_background(
    job_id: str,
    params: RetrievalParameters,
    retain_in_s3: bool,
):
    """Background task runner for data ingestion with dedicated DB session."""
    db = None
    try:
        from app.database.connection import SessionLocal
        db = SessionLocal()
    except Exception as e:
        logger.warning(f"Could not open DB session for background task: {e}")

    try:
        result = process_ingestion_job(
            job_id=job_id,
            params=params,
            db=db,
            retain_in_s3=retain_in_s3,
        )
        if job_id in _IN_MEMORY_JOBS:
            _IN_MEMORY_JOBS[job_id]["status"] = result["status"]
            _IN_MEMORY_JOBS[job_id]["result"] = result
    except Exception as exc:
        logger.error(f"[Job {job_id}] Ingestion failed in background: {exc}")
        if job_id in _IN_MEMORY_JOBS:
            _IN_MEMORY_JOBS[job_id]["status"] = "failed"
            _IN_MEMORY_JOBS[job_id]["error_summary"] = str(exc)
    finally:
        if db:
            db.close()


@router.post(
    "/copernicus/ingestions",
    status_code=status.HTTP_202_ACCEPTED,
)
def create_ingestion(
    request: IngestionRequestSchema,
    background_tasks: BackgroundTasks,
    run_synchronously: bool = Query(
        False,
        description="Set to true to wait for download and validation synchronously (for small tests)",
    ),
    db: Session = Depends(get_db),
):
    """
    Submits a validated Copernicus subset ingestion request.
    Executes retrieval, validation, provenance recording, and optional S3 retention.
    """
    params = RetrievalParameters(
        dataset_id=request.dataset_id,
        variables=request.variables,
        minimum_longitude=request.minimum_longitude,
        maximum_longitude=request.maximum_longitude,
        minimum_latitude=request.minimum_latitude,
        maximum_latitude=request.maximum_latitude,
        start_datetime=request.start_datetime,
        end_datetime=request.end_datetime,
        minimum_depth=request.minimum_depth,
        maximum_depth=request.maximum_depth,
        dataset_version=request.dataset_version,
        dataset_part=request.dataset_part,
        output_filename=request.output_filename,
    )

    try:
        # Validate parameters before creating job
        dataset = registry.get_or_raise(params.dataset_id)
        registry.validate_variables(params.dataset_id, params.variables)

        # Attempt to create DB job
        job_id = None
        try:
            job = create_ingestion_job(params=params, db=db, retain_in_s3=request.retain_in_s3)
            job_id = job.id
        except Exception as db_err:
            logger.warning(f"Database job creation skipped (using in-memory tracking): {db_err}")
            import uuid
            job_id = str(uuid.uuid4())

        # Cache in memory
        _IN_MEMORY_JOBS[job_id] = {
            "id": job_id,
            "provider": dataset.provider,
            "dataset_id": dataset.dataset_id,
            "product_id": dataset.product_id,
            "status": "queued",
            "requested_variables": params.variables,
            "requested_spatial_extent": {
                "minimum_longitude": params.minimum_longitude,
                "maximum_longitude": params.maximum_longitude,
                "minimum_latitude": params.minimum_latitude,
                "maximum_latitude": params.maximum_latitude,
            },
            "requested_time_interval": {"start": params.start_datetime, "end": params.end_datetime},
            "requested_depth_interval": {"minimum_depth": params.minimum_depth, "maximum_depth": params.maximum_depth},
            "retain_in_s3": request.retain_in_s3,
            "error_summary": None,
        }

        if run_synchronously:
            # Execute synchronously
            result = process_ingestion_job(
                job_id=job_id,
                params=params,
                db=db if hasattr(db, "is_active") and db.is_active else None,
                retain_in_s3=request.retain_in_s3,
            )
            _IN_MEMORY_JOBS[job_id]["status"] = result["status"]
            _IN_MEMORY_JOBS[job_id]["result"] = result
            return {
                "job_id": job_id,
                "status": result["status"],
                "message": "Ingestion completed synchronously.",
                "details": result,
            }
        else:
            # Dispatch to background task
            background_tasks.add_task(
                _run_ingestion_background,
                job_id=job_id,
                params=params,
                retain_in_s3=request.retain_in_s3,
            )
            return {
                "job_id": job_id,
                "status": "queued",
                "message": "Ingestion job submitted successfully.",
            }

    except (DatasetNotFoundError, InvalidVariableError, InvalidBoundsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to submit ingestion: {exc}") from exc


@router.get("/copernicus/ingestions")
def list_ingestion_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lists recent ingestion jobs."""
    try:
        db_jobs = list_jobs(db, limit=limit, status=status_filter)
        return [
            {
                "id": j.id,
                "provider": j.provider,
                "dataset_id": j.dataset_id,
                "product_id": j.product_id,
                "status": j.status,
                "requested_variables": j.requested_variables,
                "created_at": j.created_at,
                "completed_at": j.completed_at,
                "error_summary": j.error_summary,
            }
            for j in db_jobs
        ]
    except Exception as db_err:
        logger.debug(f"DB list jobs fell back to memory: {db_err}")

    # Fallback to in-memory jobs
    jobs = list(_IN_MEMORY_JOBS.values())
    if status_filter:
        jobs = [j for j in jobs if j.get("status") == status_filter]
    return jobs[:limit]


@router.get("/copernicus/ingestions/{job_id}")
def get_ingestion_job_status(job_id: str, db: Session = Depends(get_db)):
    """Returns the current status, assets, validation reports, and provenance for a job."""
    try:
        db_job = get_job(db, job_id)
        if db_job:
            assets = [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "file_format": a.file_format,
                    "file_size_bytes": a.file_size_bytes,
                    "sha256_checksum": a.sha256_checksum,
                    "storage_backend": a.storage_backend,
                    "storage_bucket": a.storage_bucket,
                    "storage_key": a.storage_key,
                    "validation_status": a.validation_status,
                }
                for a in db_job.assets
            ]
            val_reports = [
                {
                    "id": vr.id,
                    "status": vr.validation_status,
                    "dimensions": vr.dimensions,
                    "coordinates": vr.coordinates_summary,
                    "statistics": vr.statistics,
                    "warnings": vr.warnings,
                    "errors": vr.errors,
                }
                for vr in db_job.validation_reports
            ]
            prov_records = [
                {
                    "id": pr.id,
                    "provider": pr.provider,
                    "dataset_id": pr.dataset_id,
                    "retrieval_timestamp": pr.retrieval_timestamp,
                    "sha256_checksum": pr.sha256_checksum,
                    "processing_method": pr.processing_method,
                }
                for pr in db_job.provenance_records
            ]

            return {
                "id": db_job.id,
                "provider": db_job.provider,
                "dataset_id": db_job.dataset_id,
                "product_id": db_job.product_id,
                "status": db_job.status,
                "requested_variables": db_job.requested_variables,
                "requested_spatial_extent": db_job.requested_spatial_extent,
                "requested_time_interval": db_job.requested_time_interval,
                "requested_depth_interval": db_job.requested_depth_interval,
                "started_at": db_job.started_at,
                "completed_at": db_job.completed_at,
                "error_summary": db_job.error_summary,
                "created_at": db_job.created_at,
                "assets": assets,
                "validation_reports": val_reports,
                "provenance_records": prov_records,
            }
    except Exception as db_err:
        logger.debug(f"DB get job fell back to memory: {db_err}")

    if job_id in _IN_MEMORY_JOBS:
        return _IN_MEMORY_JOBS[job_id]

    raise HTTPException(status_code=404, detail=f"Ingestion job '{job_id}' not found.")


@router.post("/copernicus/ingestions/{job_id}/validate")
def validate_job_asset(job_id: str, db: Session = Depends(get_db)):
    """Runs or retrieves validation results for the downloaded file associated with a job."""
    # Check DB first
    try:
        db_job = get_job(db, job_id)
        if db_job:
            if db_job.validation_reports:
                vr = db_job.validation_reports[0]
                return {
                    "file_path": db_job.assets[0].local_staging_path if db_job.assets else None,
                    "status": vr.validation_status,
                    "is_valid": vr.validation_status in ("passed", "warnings"),
                    "cf_conventions": vr.cf_conventions,
                    "dimensions": vr.dimensions,
                    "coordinates_summary": vr.coordinates_summary,
                    "variable_stats": vr.statistics,
                    "warnings": vr.warnings,
                    "errors": vr.errors,
                }
            if db_job.assets and db_job.assets[0].local_staging_path:
                report = validator.validate_file(
                    db_job.assets[0].local_staging_path,
                    expected_dataset_id=db_job.dataset_id,
                    expected_variables=db_job.requested_variables,
                )
                return report.to_dict()
    except Exception as db_err:
        logger.debug(f"DB validate asset fallback: {db_err}")

    # Fallback to in-memory
    cached_job = _IN_MEMORY_JOBS.get(job_id)
    if cached_job and "result" in cached_job:
        val_report = cached_job["result"].get("validation_report")
        if val_report:
            return val_report

    raise HTTPException(status_code=404, detail=f"No asset found to validate for job '{job_id}'.")
