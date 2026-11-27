"""
FastAPI Routes for Oceanographic Observations: CTD Casts and ADCP Current Profiles.
"""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.modules.oceanography.parsers import oceanography_service

router = APIRouter(prefix="/oceanography", tags=["Oceanographic CTD & ADCP Profiles"])


class ProfileSummaryItem(BaseModel):
    id: str
    instrument_type: str
    station_name: str
    expedition_id: Optional[str] = None
    latitude: float
    longitude: float
    max_depth_m: Optional[float] = None
    total_levels: Optional[int] = None
    source_filename: str


class ProfileListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    profiles: List[ProfileSummaryItem]


@router.post("/profiles/ctd/upload", status_code=status.HTTP_201_CREATED)
async def upload_ctd_profile(
    file: UploadFile = File(..., description="Sea-Bird .cnv or CSV CTD cast file"),
    station_name: str = Form(..., description="Station identifier e.g. 'STN-01-ARABIAN'"),
    latitude: float = Form(..., ge=-90.0, le=90.0),
    longitude: float = Form(..., ge=-180.0, le=180.0),
    expedition_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Parses and ingests a Conductivity, Temperature, Depth (CTD) vertical profile cast.
    Supports SBE .cnv and tabular CSV formats.
    Stores raw file in SeaweedFS 'marine-research' and persists observation levels in PostgreSQL.
    """
    try:
        content_bytes = await file.read()
        content_str = content_bytes.decode("utf-8", errors="replace")

        profile, levels_count = oceanography_service.ingest_profile(
            db=db,
            instrument_type="CTD",
            station_name=station_name,
            latitude=latitude,
            longitude=longitude,
            profile_content=content_str,
            filename=file.filename or "ctd_cast.csv",
            expedition_id=expedition_id,
        )

        return {
            "status": "success",
            "profile_id": profile.id,
            "instrument_type": "CTD",
            "station_name": profile.station_name,
            "total_levels": levels_count,
            "max_depth_m": profile.max_depth_m,
            "storage_key": profile.raw_file_storage_key,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CTD parsing failed: {str(exc)}",
        )


@router.post("/profiles/adcp/upload", status_code=status.HTTP_201_CREATED)
async def upload_adcp_profile(
    file: UploadFile = File(..., description="ADCP current velocity profile CSV/DAT file"),
    station_name: str = Form(..., description="ADCP mooring / station identifier"),
    latitude: float = Form(..., ge=-90.0, le=90.0),
    longitude: float = Form(..., ge=-180.0, le=180.0),
    expedition_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Parses and ingests an Acoustic Doppler Current Profiler (ADCP) vertical current profile.
    Computes velocity magnitude and compass direction vectors from u/v components.
    """
    try:
        content_bytes = await file.read()
        content_str = content_bytes.decode("utf-8", errors="replace")

        profile, levels_count = oceanography_service.ingest_profile(
            db=db,
            instrument_type="ADCP",
            station_name=station_name,
            latitude=latitude,
            longitude=longitude,
            profile_content=content_str,
            filename=file.filename or "adcp_profile.csv",
            expedition_id=expedition_id,
        )

        return {
            "status": "success",
            "profile_id": profile.id,
            "instrument_type": "ADCP",
            "station_name": profile.station_name,
            "total_levels": levels_count,
            "max_depth_m": profile.max_depth_m,
            "storage_key": profile.raw_file_storage_key,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ADCP parsing failed: {str(exc)}",
        )


@router.get("/profiles", response_model=ProfileListResponse)
def list_profiles(
    instrument_type: Optional[str] = Query(None, description="'CTD' or 'ADCP'"),
    station_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Queries cataloged CTD and ADCP vertical profiles.
    """
    return oceanography_service.list_profiles(
        db=db,
        instrument_type=instrument_type,
        station_name=station_name,
        limit=limit,
        offset=offset,
    )


@router.get("/profiles/{profile_id}")
def get_profile_details(
    profile_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieves complete vertical profile observation levels with scientific QC flags.
    """
    profile = oceanography_service.get_profile_details(db=db, profile_id=profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Oceanographic profile '{profile_id}' not found",
        )
    return profile
