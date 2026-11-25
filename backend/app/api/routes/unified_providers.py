"""
Unified API routes for multi-provider marine data operations.

Exposes endpoints for:
- Provider discovery & capability inspection (/api/v1/providers)
- Provider dataset catalogues and search
- Dry-run / preview parameter validation
- Unified ingestion execution
- Ingestion job tracking, assets, validation reports, and provenance (/api/v1/ingestions)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import (
    IngestionJobModel,
    IngestionAssetModel,
    ValidationReportModel,
    ProvenanceRecordModel,
)
from app.modules.data_sources.base import (
    UnifiedRetrievalParams,
    UnifiedPreviewResult,
)
from app.modules.data_sources.registry import provider_registry
from app.modules.data_sources.orchestrator import unified_orchestrator
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
    InvalidBoundsError,
    RetrievalError,
    ValidationError,
)

logger = logging.getLogger(__name__)

providers_router = APIRouter(
    prefix="/api/v1/providers",
    tags=["Unified Marine Providers"],
)

ingestions_router = APIRouter(
    prefix="/api/v1/ingestions",
    tags=["Unified Marine Ingestions"],
)


# ==============================================================================
# Pydantic Schemas
# ==============================================================================
class UnifiedPreviewRequest(BaseModel):
    dataset_id: str = Field(..., description="Target dataset ID")
    variables: List[str] = Field(..., min_length=1, description="List of oceanographic variables")
    minimum_longitude: float = Field(..., description="Bounding box minimum longitude [-180, 360]")
    maximum_longitude: float = Field(..., description="Bounding box maximum longitude [-180, 360]")
    minimum_latitude: float = Field(..., ge=-90.0, le=90.0, description="Bounding box minimum latitude [-90, 90]")
    maximum_latitude: float = Field(..., ge=-90.0, le=90.0, description="Bounding box maximum latitude [-90, 90]")
    start_datetime: str = Field(..., description="Start datetime (ISO 8601, e.g. 2024-01-01T00:00:00Z)")
    end_datetime: str = Field(..., description="End datetime (ISO 8601, e.g. 2024-01-05T00:00:00Z)")
    minimum_depth: Optional[float] = Field(None, ge=0.0, description="Minimum depth/pressure level")
    maximum_depth: Optional[float] = Field(None, ge=0.0, description="Maximum depth/pressure level")


class UnifiedIngestionRequest(UnifiedPreviewRequest):
    output_filename: Optional[str] = Field(None, description="Optional custom filename for retrieved NetCDF")
    dataset_version: Optional[str] = Field(None, description="Optional dataset version")
    dataset_part: Optional[str] = Field("default", description="Dataset part/subset identifier")
    retain_in_s3: bool = Field(False, description="Persist retrieved asset in SeaweedFS S3 storage")
    asynchronous: bool = Field(False, description="Execute ingestion asynchronously via background task")


# ==============================================================================
# Provider Discovery & Catalogue Endpoints
# ==============================================================================
@providers_router.get("", response_model=List[Dict[str, Any]])
def list_providers():
    """Returns metadata and operational status for all registered marine data providers."""
    return [p.to_dict() for p in provider_registry.list_providers()]


@providers_router.get("/{provider_id}")
def get_provider_details(provider_id: str):
    """Returns detailed configuration, access method, and license for a provider."""
    try:
        provider = provider_registry.get(provider_id)
        return provider.metadata().to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@providers_router.get("/{provider_id}/datasets")
def list_provider_datasets(provider_id: str):
    """Lists all verified and registered datasets for a specific provider."""
    try:
        provider = provider_registry.get(provider_id)
        return [d.to_dict() for d in provider.list_datasets()]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@providers_router.get("/{provider_id}/datasets/{dataset_id}")
def get_provider_dataset(provider_id: str, dataset_id: str):
    """Returns complete metadata, variables, coverage, and documentation for a dataset."""
    try:
        provider = provider_registry.get(provider_id)
        return provider.get_dataset(dataset_id).to_dict()
    except (ValueError, DatasetNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@providers_router.get("/{provider_id}/search")
def search_provider_catalogue(
    provider_id: str,
    query: str = Query(..., min_length=2, description="Search keyword, e.g. sst, wind, temp, salinity"),
    data_type: Optional[str] = Query(None, description="Filter by data type"),
):
    """Searches the catalogue of a specific provider."""
    try:
        provider = provider_registry.get(provider_id)
        results = provider.search_catalogue(query, data_type=data_type)
        return {
            "provider_id": provider_id,
            "query": query,
            "total_found": len(results),
            "results": [r.to_dict() for r in results],
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ==============================================================================
# Dry-run Preview & Ingestion Endpoints
# ==============================================================================
@providers_router.post("/{provider_id}/preview")
def preview_provider_ingestion(provider_id: str, request: UnifiedPreviewRequest):
    """
    Validates bounding parameters and estimates data points and size without downloading.
    """
    try:
        params = UnifiedRetrievalParams(
            provider_id=provider_id,
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
        )
        preview_res = unified_orchestrator.preview_ingestion(params)
        return preview_res.to_dict()
    except (DatasetNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InvalidVariableError, InvalidBoundsError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview failed: {exc}") from exc


@providers_router.post("/{provider_id}/ingestions", status_code=status.HTTP_201_CREATED)
def trigger_provider_ingestion(
    provider_id: str,
    request: UnifiedIngestionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Executes or schedules an ingestion workflow for the specified provider.
    Retrieves bounded NetCDF data, computes SHA-256, validates scientific metrics,
    records provenance, and persists to PostgreSQL and optional SeaweedFS S3.
    """
    try:
        params = UnifiedRetrievalParams(
            provider_id=provider_id,
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
            output_filename=request.output_filename,
            dataset_version=request.dataset_version,
            dataset_part=request.dataset_part,
        )

        job = unified_orchestrator.create_ingestion_job(
            params=params, db=db, retain_in_s3=request.retain_in_s3
        )

        if request.asynchronous:
            background_tasks.add_task(
                unified_orchestrator.run_ingestion_job,
                job_id=job.id,
                params=params,
                db=db,
                retain_in_s3=request.retain_in_s3,
            )
            return {
                "job_id": job.id,
                "status": "pending",
                "message": f"Ingestion job {job.id} dispatched asynchronously.",
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
        else:
            result = unified_orchestrator.run_ingestion_job(
                job_id=job.id,
                params=params,
                db=db,
                retain_in_s3=request.retain_in_s3,
            )
            return result

    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InvalidVariableError, InvalidBoundsError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RetrievalError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Ingestion execution error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ==============================================================================
# Ingestion Job Management Endpoints (/api/v1/ingestions)
# ==============================================================================
@ingestions_router.get("")
def list_ingestion_jobs(
    provider: Optional[str] = Query(None, description="Filter by provider"),
    status: Optional[str] = Query(None, description="Filter by status (pending, running, completed, failed)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Lists ingestion jobs with filtering by provider and status."""
    jobs = unified_orchestrator.list_jobs(db=db, provider=provider, status=status, limit=limit, offset=offset)
    return [
        {
            "id": j.id,
            "provider": j.provider,
            "product_id": j.product_id,
            "dataset_id": j.dataset_id,
            "status": j.status,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "error_summary": j.error_summary,
        }
        for j in jobs
    ]


@ingestions_router.get("/{job_id}")
def get_ingestion_job(job_id: str, db: Session = Depends(get_db)):
    """Retrieves full details of an ingestion job."""
    job = unified_orchestrator.get_job(job_id, db)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    return {
        "id": job.id,
        "provider": job.provider,
        "product_id": job.product_id,
        "dataset_id": job.dataset_id,
        "dataset_version": job.dataset_version,
        "dataset_part": job.dataset_part,
        "requested_variables": job.requested_variables,
        "requested_spatial_extent": job.requested_spatial_extent,
        "requested_time_interval": job.requested_time_interval,
        "requested_depth_interval": job.requested_depth_interval,
        "request_parameters": job.request_parameters,
        "status": job.status,
        "error_summary": job.error_summary,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@ingestions_router.get("/{job_id}/assets")
def get_ingestion_assets(job_id: str, db: Session = Depends(get_db)):
    """Retrieves binary assets (NetCDF files, hashes, storage locations) for a job."""
    job = unified_orchestrator.get_job(job_id, db)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    assets = unified_orchestrator.get_job_assets(job_id, db)
    return [
        {
            "id": a.id,
            "job_id": a.job_id,
            "filename": a.filename,
            "file_format": a.file_format,
            "file_size_bytes": a.file_size_bytes,
            "sha256_checksum": a.sha256_checksum,
            "storage_backend": a.storage_backend,
            "storage_bucket": a.storage_bucket,
            "storage_key": a.storage_key,
            "local_staging_path": a.local_staging_path,
            "validation_status": a.validation_status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in assets
    ]


@ingestions_router.get("/{job_id}/validation")
def get_ingestion_validation(job_id: str, db: Session = Depends(get_db)):
    """Retrieves scientific validation reports and variable statistics for a job."""
    job = unified_orchestrator.get_job(job_id, db)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    reports = unified_orchestrator.get_job_validation(job_id, db)
    return [
        {
            "id": r.id,
            "job_id": r.job_id,
            "asset_id": r.asset_id,
            "validation_status": r.validation_status,
            "variables_validated": r.variables_validated,
            "dimensions": r.dimensions,
            "coordinates_summary": r.coordinates_summary,
            "valid_points_count": r.valid_points_count,
            "missing_points_count": r.missing_points_count,
            "invalid_points_count": r.invalid_points_count,
            "statistics": r.statistics,
            "cf_conventions": r.cf_conventions,
            "warnings": r.warnings,
            "errors": r.errors,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


@ingestions_router.get("/{job_id}/provenance")
def get_ingestion_provenance(job_id: str, db: Session = Depends(get_db)):
    """Retrieves scientific lineage, citation, DOI, and processing method for a job."""
    job = unified_orchestrator.get_job(job_id, db)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    records = unified_orchestrator.get_job_provenance(job_id, db)
    return [
        {
            "id": p.id,
            "job_id": p.job_id,
            "provider": p.provider,
            "product_id": p.product_id,
            "dataset_id": p.dataset_id,
            "dataset_version": p.dataset_version,
            "provider_doi": p.provider_doi,
            "retrieval_timestamp": p.retrieval_timestamp.isoformat() if p.retrieval_timestamp else None,
            "requested_date_range": p.requested_date_range,
            "actual_data_date_range": p.actual_data_date_range,
            "spatial_extent": p.spatial_extent,
            "variables": p.variables,
            "units": p.units,
            "processing_method": p.processing_method,
            "source_licence": p.source_licence,
            "toolbox_version": p.toolbox_version,
            "sha256_checksum": p.sha256_checksum,
            "validation_report_id": p.validation_report_id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in records
    ]
