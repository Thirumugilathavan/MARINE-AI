"""
Marine Image and Underwater Video Management Service.

Handles:
- Storage of high-resolution ROV/AUV underwater survey footage, benthic stills,
  and satellite imagery in the SeaweedFS 'marine-media' bucket.
- Relational metadata indexing in PostgreSQL (coordinates, depth, sensor, tags).
- Presigned download and streaming URL generation.
"""

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Any
import uuid

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.database.models import MarineMediaAssetModel
from app.modules.research_files.upload_service import upload_service
from app.storage.s3_client import s3_client

logger = logging.getLogger(__name__)


class MarineMediaService:
    """Service managing marine images, ROV video footage, and underwater observations."""

    def register_media_asset(
        self,
        db: Session,
        project_id: str,
        filename: str,
        file_bytes: bytes,
        mime_type: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        depth_meters: Optional[float] = None,
        captured_at: Optional[datetime] = None,
        expedition_id: Optional[str] = None,
        sample_id: Optional[str] = None,
        camera_sensor_info: Optional[str] = None,
        description: Optional[str] = None,
        licence: Optional[str] = "Open Marine Research Data",
        media_metadata: Optional[Dict[str, Any]] = None,
    ) -> MarineMediaAssetModel:
        """
        Uploads media file to SeaweedFS 'marine-media' bucket and persists
        rich oceanographic and sensor metadata in PostgreSQL.
        """
        # Upload using upload_service to 'marine-media'
        upload_res = upload_service.upload_file(
            filename=filename,
            file_bytes=file_bytes,
            mime_type=mime_type,
            bucket_override="marine-media",
            category_override="media",
        )

        geom_val = None
        if latitude is not None and longitude is not None and db.bind and db.bind.dialect.name == "postgresql":
            geom_val = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)

        asset = MarineMediaAssetModel(
            id=str(uuid.uuid4()),
            project_id=project_id,
            expedition_id=expedition_id,
            sample_id=sample_id,
            filename=upload_res["filename"],
            bucket_name=upload_res["bucket_name"],
            storage_key=upload_res["storage_key"],
            mime_type=upload_res["mime_type"],
            file_size_bytes=upload_res["file_size_bytes"],
            sha256_checksum=upload_res["sha256_checksum"],
            geom=geom_val,
            latitude=latitude,
            longitude=longitude,
            depth_meters=depth_meters,
            captured_at=captured_at or datetime.now(timezone.utc),
            camera_sensor_info=camera_sensor_info,
            description=description,
            licence=licence,
            processing_status="active",
            media_metadata=media_metadata or {},
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset

    def list_assets(
        self,
        db: Session,
        project_id: Optional[str] = None,
        expedition_id: Optional[str] = None,
        mime_prefix: Optional[str] = None,  # e.g. 'image/' or 'video/'
        min_depth: Optional[float] = None,
        max_depth: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Queries media assets with filtering."""
        query = select(MarineMediaAssetModel)
        count_query = select(func.count(MarineMediaAssetModel.id))

        filters = []
        if project_id:
            filters.append(MarineMediaAssetModel.project_id == project_id)
        if expedition_id:
            filters.append(MarineMediaAssetModel.expedition_id == expedition_id)
        if mime_prefix:
            filters.append(MarineMediaAssetModel.mime_type.startswith(mime_prefix))
        if min_depth is not None:
            filters.append(MarineMediaAssetModel.depth_meters >= min_depth)
        if max_depth is not None:
            filters.append(MarineMediaAssetModel.depth_meters <= max_depth)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = db.scalar(count_query) or 0
        records = db.execute(query.order_by(MarineMediaAssetModel.created_at.desc()).offset(offset).limit(limit)).scalars().all()

        items = []
        for a in records:
            items.append({
                "id": a.id,
                "project_id": a.project_id,
                "expedition_id": a.expedition_id,
                "filename": a.filename,
                "bucket_name": a.bucket_name,
                "storage_key": a.storage_key,
                "mime_type": a.mime_type,
                "file_size_bytes": a.file_size_bytes,
                "sha256_checksum": a.sha256_checksum,
                "latitude": a.latitude,
                "longitude": a.longitude,
                "depth_meters": a.depth_meters,
                "captured_at": a.captured_at.isoformat() if a.captured_at else None,
                "camera_sensor_info": a.camera_sensor_info,
                "description": a.description,
                "media_metadata": a.media_metadata,
            })

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "assets": items,
        }

    def get_asset(self, db: Session, asset_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves single asset record by ID."""
        a = db.execute(
            select(MarineMediaAssetModel).where(MarineMediaAssetModel.id == asset_id)
        ).scalar_one_or_none()
        if not a:
            return None

        return {
            "id": a.id,
            "project_id": a.project_id,
            "expedition_id": a.expedition_id,
            "sample_id": a.sample_id,
            "filename": a.filename,
            "bucket_name": a.bucket_name,
            "storage_key": a.storage_key,
            "mime_type": a.mime_type,
            "file_size_bytes": a.file_size_bytes,
            "sha256_checksum": a.sha256_checksum,
            "latitude": a.latitude,
            "longitude": a.longitude,
            "depth_meters": a.depth_meters,
            "captured_at": a.captured_at.isoformat() if a.captured_at else None,
            "camera_sensor_info": a.camera_sensor_info,
            "description": a.description,
            "licence": a.licence,
            "processing_status": a.processing_status,
            "media_metadata": a.media_metadata,
        }


media_service = MarineMediaService()
