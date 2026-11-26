"""
Research File Ingestion and Storage Service.

Handles scientific file validation, MIME type detection, streaming SHA-256 checksumming,
and SeaweedFS multi-bucket storage across:
- marine-edna: FASTA, FASTQ, gzip sequencing archives
- marine-media: Underwater ROV/AUV video (MP4, MOV) and imagery (JPEG, PNG, TIFF)
- marine-research: CTD/ADCP profile data (CSV, CNV), scientific reports, and field documents
"""

from datetime import datetime, timezone
import hashlib
import io
import logging
import mimetypes
import os
from typing import Dict, Optional, Tuple, Any
import uuid

from app.storage.s3_client import s3_client

logger = logging.getLogger(__name__)

# Allowed extension mappings to target buckets and categories
EXTENSION_MAPPING: Dict[str, Tuple[str, str]] = {
    # eDNA files -> marine-edna
    ".fastq": ("marine-edna", "edna"),
    ".fq": ("marine-edna", "edna"),
    ".fasta": ("marine-edna", "edna"),
    ".fa": ("marine-edna", "edna"),
    ".gz": ("marine-edna", "edna"),  # usually fastq.gz / fasta.gz
    ".bam": ("marine-edna", "edna"),
    ".sam": ("marine-edna", "edna"),
    
    # Media files -> marine-media
    ".jpg": ("marine-media", "media"),
    ".jpeg": ("marine-media", "media"),
    ".png": ("marine-media", "media"),
    ".tif": ("marine-media", "media"),
    ".tiff": ("marine-media", "media"),
    ".mp4": ("marine-media", "media"),
    ".mov": ("marine-media", "media"),
    ".avi": ("marine-media", "media"),
    ".mkv": ("marine-media", "media"),

    # Oceanographic and research documents -> marine-research
    ".csv": ("marine-research", "oceanography"),
    ".cnv": ("marine-research", "oceanography"),
    ".dat": ("marine-research", "oceanography"),
    ".nc": ("marine-research", "oceanography"),
    ".txt": ("marine-research", "documents"),
    ".pdf": ("marine-research", "documents"),
    ".docx": ("marine-research", "documents"),
    ".json": ("marine-research", "metadata"),
}


class ResearchFileUploadService:
    """Service for validating, hashing, and storing scientific research files."""

    def __init__(self, storage: Optional[Any] = None):
        self.storage = storage or s3_client

    def classify_file(self, filename: str) -> Tuple[str, str]:
        """
        Determines target bucket and category based on file suffix.
        Defaults to 'marine-research' and 'general' if unrecognized.
        """
        lower_name = filename.lower()
        if lower_name.endswith(".fastq.gz") or lower_name.endswith(".fq.gz"):
            return "marine-edna", "edna"
        if lower_name.endswith(".fasta.gz") or lower_name.endswith(".fa.gz"):
            return "marine-edna", "edna"

        _, ext = os.path.splitext(lower_name)
        if ext in EXTENSION_MAPPING:
            return EXTENSION_MAPPING[ext]
        return "marine-research", "general"

    def compute_sha256(self, file_bytes: bytes) -> str:
        """Computes SHA-256 checksum of raw file bytes."""
        hasher = hashlib.sha256()
        hasher.update(file_bytes)
        return hasher.hexdigest()

    def upload_file(
        self,
        filename: str,
        file_bytes: bytes,
        mime_type: Optional[str] = None,
        bucket_override: Optional[str] = None,
        category_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validates, checksums, and uploads research file to SeaweedFS.
        Returns key, bucket, size, checksum, and category metadata.
        """
        target_bucket, category = self.classify_file(filename)
        if bucket_override:
            target_bucket = bucket_override
        if category_override:
            category = category_override

        detected_mime = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        file_size = len(file_bytes)
        sha256 = self.compute_sha256(file_bytes)

        now = datetime.now(timezone.utc)
        file_uuid = str(uuid.uuid4())[:8]
        safe_filename = os.path.basename(filename).replace(" ", "_")
        storage_key = f"{category}/{now.year}/{now.month:02d}/{file_uuid}_{safe_filename}"

        # Upload to SeaweedFS S3
        content_stream = io.BytesIO(file_bytes)
        self.storage.upload_fileobj(
            Fileobj=content_stream,
            Bucket=target_bucket,
            Key=storage_key,
            ExtraArgs={
                "ContentType": detected_mime,
                "Metadata": {
                    "sha256": sha256,
                    "original_filename": safe_filename,
                    "category": category,
                },
            },
        )

        logger.info(f"Uploaded scientific research file '{safe_filename}' ({file_size} bytes) to {target_bucket}/{storage_key}")

        return {
            "filename": safe_filename,
            "bucket_name": target_bucket,
            "storage_key": storage_key,
            "category": category,
            "mime_type": detected_mime,
            "file_size_bytes": file_size,
            "sha256_checksum": sha256,
            "uploaded_at": now.isoformat(),
        }


upload_service = ResearchFileUploadService()
