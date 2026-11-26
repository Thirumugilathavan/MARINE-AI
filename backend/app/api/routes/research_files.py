"""
FastAPI Routes for Scientific Research File Ingestion.
Supports multi-category scientific file uploads (eDNA, media, oceanography, documents)
with MIME verification and SHA-256 streaming checksumming.
"""

from typing import Optional
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, status

from app.modules.research_files.upload_service import upload_service

router = APIRouter(prefix="/research-files", tags=["Research Files"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_research_file(
    file: UploadFile = File(..., description="Research file to upload"),
    bucket: Optional[str] = Form(None, description="Override target bucket (e.g. marine-edna, marine-media, marine-research)"),
    category: Optional[str] = Form(None, description="Override category directory prefix"),
):
    """
    Ingests research files into SeaweedFS S3 storage.
    Automatically classifies files (e.g. FASTQ -> marine-edna, video/image -> marine-media,
    CSV/CNV -> marine-research) and computes streaming SHA-256 checksums.
    """
    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        result = upload_service.upload_file(
            filename=file.filename or "unknown.dat",
            file_bytes=content,
            mime_type=file.content_type,
            bucket_override=bucket,
            category_override=category,
        )
        return {
            "status": "success",
            "file": result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(exc)}",
        )
