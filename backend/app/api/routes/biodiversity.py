"""
Marine Biodiversity API Endpoints (OBIS and GBIF).
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.modules.data_sources.biodiversity.service import (
    obis_service,
    gbif_service,
    reconciliation_engine,
)

router = APIRouter(prefix="/biodiversity", tags=["Marine Biodiversity (OBIS / GBIF)"])


class OccurrenceQueryRequest(BaseModel):
    scientific_name: Optional[str] = Field(None, example="Thunnus albacares")
    provider: str = Field("all", description="Source provider: 'obis', 'gbif', or 'all'", example="all")
    min_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, example=60.0)
    min_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, example=10.0)
    max_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, example=75.0)
    max_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, example=20.0)
    start_date: Optional[str] = Field(None, example="2020-01-01")
    end_date: Optional[str] = Field(None, example="2024-12-31")
    limit: int = Field(50, ge=1, le=500, example=20)


class OccurrenceIngestRequest(OccurrenceQueryRequest):
    reconcile_after_ingest: bool = Field(True, description="Run cross-provider reconciliation after insertion")


class OccurrenceResponse(BaseModel):
    id: str
    provider: str
    occurrence_id: str
    scientific_name: str
    accepted_scientific_name: Optional[str] = None
    aphia_id: Optional[int] = None
    latitude: float
    longitude: float
    depth_meters: Optional[float] = None
    event_date: Optional[str] = None
    basis_of_record: Optional[str] = None
    institution_code: Optional[str] = None
    dataset_name: Optional[str] = None
    licence: Optional[str] = None
    is_reconciled: bool = False
    reconciled_cluster_id: Optional[str] = None

    class Config:
        from_attributes = True


@router.post("/occurrences/query", response_model=Dict[str, Any])
def query_live_occurrences(req: OccurrenceQueryRequest):
    """
    Queries live external biodiversity sources (OBIS and/or GBIF) in real time
    without persisting to the database.
    """
    records = []
    prov = req.provider.lower()

    if prov in ("obis", "all"):
        try:
            obis_recs = obis_service.search_occurrences(
                scientific_name=req.scientific_name,
                min_longitude=req.min_longitude,
                min_latitude=req.min_latitude,
                max_longitude=req.max_longitude,
                max_latitude=req.max_latitude,
                start_date=req.start_date,
                end_date=req.end_date,
                size=req.limit,
            )
            records.extend(obis_recs)
        except Exception as e:
            if prov == "obis":
                raise HTTPException(status_code=502, detail=f"OBIS query failed: {e}")

    if prov in ("gbif", "all"):
        try:
            gbif_recs = gbif_service.search_occurrences(
                scientific_name=req.scientific_name,
                min_longitude=req.min_longitude,
                min_latitude=req.min_latitude,
                max_longitude=req.max_longitude,
                max_latitude=req.max_latitude,
                limit=req.limit,
            )
            records.extend(gbif_recs)
        except Exception as e:
            if prov == "gbif":
                raise HTTPException(status_code=502, detail=f"GBIF query failed: {e}")

    return {
        "query": req.model_dump(),
        "total_returned": len(records),
        "results": records[:req.limit],
    }


@router.post("/occurrences/ingest", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def ingest_occurrences(req: OccurrenceIngestRequest, db: Session = Depends(get_db)):
    """
    Fetches real occurrences from OBIS / GBIF and persists them with PostGIS spatial geometry.
    Optionally triggers cross-provider deduplication and reconciliation.
    """
    # 1. Fetch live
    fetch_resp = query_live_occurrences(req)
    raw_records = fetch_resp["results"]

    # 2. Persist to PostGIS
    inserted = reconciliation_engine.persist_occurrences(db, raw_records)

    # 3. Optional reconciliation
    reconciliation_summary = None
    if req.reconcile_after_ingest and inserted > 0:
        reconciliation_summary = reconciliation_engine.reconcile_duplicates(
            db, scientific_name=req.scientific_name
        )

    return {
        "status": "success",
        "records_fetched": len(raw_records),
        "records_newly_inserted": inserted,
        "reconciliation": reconciliation_summary,
    }


@router.get("/occurrences/search", response_model=List[OccurrenceResponse])
def search_occurrences(
    scientific_name: Optional[str] = Query(None, description="Species or taxon name to search"),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=180.0),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=180.0),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    provider: Optional[str] = Query(None, description="'obis' or 'gbif'"),
    year: Optional[int] = Query(None, ge=1800, le=2100),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Searches structured occurrence records stored in PostgreSQL/PostGIS.
    Supports bounding-box spatial queries and taxonomy filtering.
    """
    return reconciliation_engine.search_persisted_occurrences(
        db=db,
        scientific_name=scientific_name,
        min_longitude=min_lon,
        min_latitude=min_lat,
        max_longitude=max_lon,
        max_latitude=max_lat,
        provider=provider,
        year=year,
        limit=limit,
        offset=offset,
    )


@router.post("/occurrences/reconcile", response_model=Dict[str, Any])
def trigger_reconciliation(
    distance_threshold_km: float = Query(5.0, ge=0.1, le=50.0),
    scientific_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Runs spatial and taxonomic reconciliation across OBIS and GBIF occurrences to identify duplicates.
    """
    return reconciliation_engine.reconcile_duplicates(
        db, distance_threshold_km=distance_threshold_km, scientific_name=scientific_name
    )
