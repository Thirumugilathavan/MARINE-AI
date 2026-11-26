"""
FastAPI Routes for Marine Images and Underwater Video Management.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.modules.media.service import media_service

router = APIRouter(prefix="/media", tags=["Marine Media (Images & Underwater Video)"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_media_asset(
    file: UploadFile = File(..., description="Image (PNG/JPEG/TIFF) or Video (MP4/MOV) file"),
    project_id: str = Form(..., description="Project / Cruise ID"),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    depth_meters: Optional[float] = Form(None),
    expedition_id: Optional[str] = Form(None),
    camera_sensor_info: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Uploads marine image or ROV/AUV underwater video to the 'marine-media' SeaweedFS bucket
    and registers metadata (coordinates, depth, camera sensor) in PostgreSQL.
    """
    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        asset = media_service.register_media_asset(
            db=db,
            project_id=project_id,
            filename=file.filename or "media_asset.dat",
            file_bytes=content,
            mime_type=file.content_type,
            latitude=latitude,
            longitude=longitude,
            depth_meters=depth_meters,
            expedition_id=expedition_id,
            camera_sensor_info=camera_sensor_info,
            description=description,
        )

        return {
            "status": "success",
            "asset_id": asset.id,
            "filename": asset.filename,
            "storage_key": asset.storage_key,
            "bucket_name": asset.bucket_name,
            "mime_type": asset.mime_type,
            "file_size_bytes": asset.file_size_bytes,
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Media upload failed: {str(exc)}",
        )


@router.get("/assets")
def list_media_assets(
    project_id: Optional[str] = Query(None),
    expedition_id: Optional[str] = Query(None),
    mime_prefix: Optional[str] = Query(None, description="'image/' or 'video/'"),
    min_depth: Optional[float] = Query(None, description="Minimum depth in meters"),
    max_depth: Optional[float] = Query(None, description="Maximum depth in meters"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Queries cataloged marine media assets with oceanographic depth and project filters.
    """
    return media_service.list_assets(
        db=db,
        project_id=project_id,
        expedition_id=expedition_id,
        mime_prefix=mime_prefix,
        min_depth=min_depth,
        max_depth=max_depth,
        limit=limit,
        offset=offset,
    )


@router.get("/assets/{asset_id}")
def get_media_asset_details(
    asset_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieves metadata for a specific media asset.
    """
    asset = media_service.get_asset(db=db, asset_id=asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset '{asset_id}' not found",
        )
    return asset
