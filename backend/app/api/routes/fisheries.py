"""
FastAPI Routes for FAO Fisheries & Aquaculture Statistics.
Provides FAO Major Fishing Areas (Area 51, 57, etc.), capture production and
aquaculture statistics querying, ingestion, and aggregation.
"""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import FisheriesStatisticModel
from app.modules.data_sources.fao.service import fao_service

router = APIRouter(prefix="/fisheries", tags=["FAO Fisheries & Aquaculture"])


class FisheriesIngestRecord(BaseModel):
    country_iso3: str = Field(..., max_length=3, description="ISO3 country code (e.g. IND, MDV)")
    country_name: str
    fao_major_area: Optional[str] = Field(None, description="e.g. Area 51 - Western Indian Ocean")
    species_scientific_name: Optional[str] = None
    species_common_name: Optional[str] = None
    species_alpha3_code: Optional[str] = Field(None, max_length=8, description="FAO 3-alpha code e.g. YFT")
    production_type: str = Field("capture", description="'capture' or 'aquaculture'")
    environment: Optional[str] = Field("marine", description="'marine', 'brackish', 'inland'")
    year: int = Field(..., ge=1950, le=2050)
    quantity_tonnes: float = Field(..., ge=0.0)
    unit: str = "tonnes"
    source_dataset: str = "FAO FishStat"
    licence: Optional[str] = "FAO Open Data Policy"


class FisheriesIngestRequest(BaseModel):
    records: List[FisheriesIngestRecord]


class FisheriesStatisticItem(BaseModel):
    id: str
    country_iso3: str
    country_name: str
    fao_major_area: Optional[str] = None
    species_scientific_name: Optional[str] = None
    species_common_name: Optional[str] = None
    species_alpha3_code: Optional[str] = None
    production_type: str
    environment: Optional[str] = None
    year: int
    quantity_tonnes: float
    unit: str
    source_dataset: str


class FisheriesStatisticListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    statistics: List[FisheriesStatisticItem]


class FisheriesSummaryItem(BaseModel):
    country_iso3: str
    country_name: str
    production_type: str
    year: int
    total_tonnes: float


class FisheriesSummaryResponse(BaseModel):
    summary: List[FisheriesSummaryItem]


@router.get("/areas")
def get_fao_major_areas(
    ocean: Optional[str] = Query(None, description="Filter by Ocean (e.g. 'Indian', 'Pacific')")
):
    """
    Retrieves FAO Major Fishing Areas.
    Queries the official FAO GeoServer OGC WFS endpoint with fallback to reference catalog.
    """
    areas = fao_service.get_major_areas(target_ocean=ocean)
    return {
        "ocean_filter": ocean,
        "count": len(areas),
        "areas": areas,
    }


@router.get("/statistics", response_model=FisheriesStatisticListResponse)
def query_fisheries_statistics(
    country_iso3: Optional[str] = Query(None, description="ISO3 code (e.g. IND)"),
    fao_major_area: Optional[str] = Query(None, description="FAO Area substring e.g. '51' or 'Western Indian'"),
    species_alpha3: Optional[str] = Query(None, description="FAO species 3-alpha code e.g. 'YFT'"),
    production_type: Optional[str] = Query(None, description="'capture' or 'aquaculture'"),
    year: Optional[int] = Query(None, description="Harvest year"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Queries persisted FAO fisheries and aquaculture production statistics from PostgreSQL.
    """
    return fao_service.query_statistics(
        db=db,
        country_iso3=country_iso3,
        fao_major_area=fao_major_area,
        species_alpha3=species_alpha3,
        production_type=production_type,
        year=year,
        limit=limit,
        offset=offset,
    )


@router.post("/seed", status_code=status.HTTP_201_CREATED)
def seed_baseline_fisheries(db: Session = Depends(get_db)):
    """
    Seeds authoritative FAO baseline capture and aquaculture production data
    for the Indian Ocean littoral states (India, Maldives, Sri Lanka).
    """
    count = fao_service.seed_baseline_statistics(db=db)
    return {
        "status": "success",
        "message": f"Seeded {count} baseline FAO statistics records",
        "new_records_count": count,
    }


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
def ingest_fisheries_statistics(
    request: FisheriesIngestRequest,
    db: Session = Depends(get_db),
):
    """
    Ingests an arbitrary batch of FAO fisheries or aquaculture statistics records.
    """
    if not request.records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Records list cannot be empty",
        )

    records_dicts = [r.model_dump() for r in request.records]
    count = fao_service.ingest_records(db=db, records=records_dicts)
    return {
        "status": "success",
        "ingested_count": count,
    }


@router.get("/summary", response_model=FisheriesSummaryResponse)
def get_fisheries_summary(
    country_iso3: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Aggregates total tonnes produced grouped by country and production type.
    """
    filters = []
    if country_iso3:
        filters.append(func.upper(FisheriesStatisticModel.country_iso3) == country_iso3.upper())
    if year:
        filters.append(FisheriesStatisticModel.year == year)

    stmt = select(
        FisheriesStatisticModel.country_iso3,
        FisheriesStatisticModel.country_name,
        FisheriesStatisticModel.production_type,
        FisheriesStatisticModel.year,
        func.sum(FisheriesStatisticModel.quantity_tonnes).label("total_tonnes"),
    )
    if filters:
        stmt = stmt.where(and_(*filters))

    stmt = stmt.group_by(
        FisheriesStatisticModel.country_iso3,
        FisheriesStatisticModel.country_name,
        FisheriesStatisticModel.production_type,
        FisheriesStatisticModel.year,
    ).order_by(FisheriesStatisticModel.country_iso3)

    rows = db.execute(stmt).all()
    summary = []
    for r in rows:
        summary.append({
            "country_iso3": r[0],
            "country_name": r[1],
            "production_type": r[2],
            "year": r[3],
            "total_tonnes": float(r[4] or 0.0),
        })

    return {
        "summary": summary,
    }
