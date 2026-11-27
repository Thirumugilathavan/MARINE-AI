"""
FastAPI Routes for Central Scientific Dataset Catalogue.
Provides 9-provider dataset discovery, variable inventories, and 7-stage
verification lifecycle status tracking.
"""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.modules.catalogue.service import catalogue_service, LIFECYCLE_STAGES

router = APIRouter(prefix="/catalogue", tags=["Scientific Dataset Catalogue"])


class LifecycleUpdateRequest(BaseModel):
    status: str = Field(..., description=f"New lifecycle status: {LIFECYCLE_STAGES}")
    quality_notes: Optional[str] = Field(None, description="Detailed verification or validation remarks")


class CatalogueDatasetItem(BaseModel):
    id: str
    provider_id: str
    dataset_name: str
    dataset_description: Optional[str] = None
    official_source_url: Optional[str] = None
    target_variables: Optional[List[str]] = None
    verification_lifecycle_status: str
    sample_asset_path: Optional[str] = None
    quality_notes: Optional[str] = None


class CatalogueListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    datasets: List[CatalogueDatasetItem]


class CatalogueSummaryResponse(BaseModel):
    total_datasets: int
    providers_count: int
    by_provider: Dict[str, Dict[str, int]]
    by_lifecycle_stage: Optional[Dict[str, int]] = None


@router.get("/datasets", response_model=CatalogueListResponse)
def list_datasets(
    provider_id: Optional[str] = Query(None, description="Filter by provider (e.g. copernicus, noaa, argo, gebco, worms, etc.)"),
    lifecycle_status: Optional[str] = Query(None, description="Filter by verification lifecycle status"),
    variable: Optional[str] = Query(None, description="Filter by scientific variable (e.g. thetao, sst, TEMP)"),
    search: Optional[str] = Query(None, description="Substring search in title or description"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Lists and searches across the central catalogue of scientific datasets.
    Covers all 9 official marine data providers.
    """
    return catalogue_service.list_datasets(
        db=db,
        provider_id=provider_id,
        lifecycle_status=lifecycle_status,
        variable=variable,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/datasets/{dataset_id}", response_model=CatalogueDatasetItem)
def get_dataset_details(
    dataset_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieves full metadata, variable units, spatial/temporal bounds,
    and current verification lifecycle status for a dataset.
    """
    entry = catalogue_service.get_dataset(db=db, dataset_id=dataset_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in central catalogue",
        )
    return entry


@router.post("/seed", status_code=status.HTTP_201_CREATED)
def seed_dataset_catalogue(db: Session = Depends(get_db)):
    """
    Seeds or updates authoritative catalog entries for all 9 integrated marine providers.
    """
    count = catalogue_service.seed_catalogue(db=db)
    return {
        "status": "success",
        "message": f"Seeded / updated {count} datasets across 9 scientific providers",
        "datasets_count": count,
    }


@router.patch("/datasets/{dataset_id}/lifecycle")
def update_dataset_lifecycle(
    dataset_id: str,
    payload: LifecycleUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Transitions dataset verification status across the 7-stage lifecycle:
    'discovered' -> 'metadata_verified' -> 'access_tested' -> 'sample_validated' -> 'production_approved'.
    """
    try:
        updated = catalogue_service.update_lifecycle(
            db=db,
            dataset_id=dataset_id,
            new_status=payload.status,
            quality_notes=payload.quality_notes,
        )
        return {
            "status": "success",
            "dataset": updated,
        }
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get("/summary", response_model=CatalogueSummaryResponse)
def get_catalogue_summary(db: Session = Depends(get_db)):
    """
    Returns high-level summary of catalogue entries by provider and lifecycle stage.
    """
    return catalogue_service.get_summary(db=db)
