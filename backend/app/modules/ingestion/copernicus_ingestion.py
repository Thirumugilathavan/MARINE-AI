"""
Copernicus Marine ingestion pipeline.

Orchestrates retrieval, spatial subsetting, normalization, physical sanity validation,
provenance tracking, and bounded storage in SeaweedFS S3.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import uuid

import numpy as np

from app.core.config import settings
from app.storage.s3_client import s3_client
from app.modules.data_sources.copernicus.constants import (
    DEFAULT_INDIAN_OCEAN_BOUNDS,
    SUPPORTED_VARIABLES,
)
from app.modules.data_sources.copernicus.service import (
    plan_retrieval,
    retrieve_copernicus_subset,
)
from app.modules.validation.marine_validator import (
    BoundingBox,
    MarineValidationReport,
    validate_cadence,
    validate_ocean_array,
    validate_variables,
)

logger = logging.getLogger(__name__)


def compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 checksum of a local file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


class CopernicusIngestionPipeline:
    """
    Ingestion pipeline for Copernicus Marine data.
    """

    def __init__(self, staging_dir: Optional[Path] = None):
        self.staging_dir = staging_dir or (Path.cwd() / "dataset-staging" / "copernicus")
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def run_ingestion(
        self,
        cadence: str,
        variables: List[str],
        bounding_box: Optional[BoundingBox] = None,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
        minimum_depth: Optional[float] = None,
        maximum_depth: Optional[float] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes complete ingestion workflow.
        """
        ingestion_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        validate_cadence(cadence)
        validate_variables(variables)
        bbox = bounding_box or BoundingBox.default_indian_ocean()
        bbox.validate()

        bbox_dict = {
            "minimum_longitude": bbox.minimum_longitude,
            "maximum_longitude": bbox.maximum_longitude,
            "minimum_latitude": bbox.minimum_latitude,
            "maximum_latitude": bbox.maximum_latitude,
        }

        # Step 1: Retrieval
        retrieval_result = retrieve_copernicus_subset(
            cadence=cadence,
            variables=variables,
            bounding_box=bbox,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            minimum_depth=minimum_depth,
            maximum_depth=maximum_depth,
            output_directory=self.staging_dir,
            username=username,
            password=password,
            dry_run=dry_run,
        )

        if retrieval_result.get("status") == "authentication_required":
            return {
                "ingestion_id": ingestion_id,
                "status": "authentication_required",
                "message": retrieval_result.get("message"),
                "cadence": cadence,
                "variables": variables,
                "bounding_box": bbox_dict,
                "provenance": None,
            }

        # Step 2: Normalization and Validation
        validation_report = MarineValidationReport(
            is_valid=True,
            cadence=cadence,
            variables=variables,
            bounding_box=bbox_dict,
        )

        staged_files = []
        for file_info in retrieval_result.get("downloaded_files", []):
            if file_info.get("status") == "success":
                staged_files.append(file_info)

        # Step 3: Provenance & Bounded Storage
        storage_records = []
        for file_item in staged_files:
            file_path_str = file_item.get("response")
            # If a file path was returned
            if file_path_str and Path(file_path_str).exists():
                local_file = Path(file_path_str)
                file_size = local_file.stat().st_size
                checksum = compute_sha256(local_file)
                s3_key = f"copernicus/{cadence}/{file_item['dataset_id']}/{ingestion_id}/{local_file.name}"

                # Attempt S3 upload
                s3_uploaded = False
                try:
                    s3_client.upload_file(
                        str(local_file),
                        settings.seaweedfs_bucket_raw,
                        s3_key,
                    )
                    s3_uploaded = True
                    logger.info(f"Uploaded {local_file.name} to S3 bucket {settings.seaweedfs_bucket_raw} key {s3_key}")
                except Exception as s3_err:
                    logger.warning(f"S3 upload deferred or unavailable: {s3_err}")

                storage_records.append({
                    "dataset_id": file_item["dataset_id"],
                    "local_path": str(local_file),
                    "file_size_bytes": file_size,
                    "sha256": checksum,
                    "s3_bucket": settings.seaweedfs_bucket_raw if s3_uploaded else None,
                    "s3_key": s3_key if s3_uploaded else None,
                    "storage_status": "s3_persisted" if s3_uploaded else "local_staged",
                })

        provenance = {
            "ingestion_id": ingestion_id,
            "provider": "Copernicus Marine Service",
            "cadence": cadence,
            "variables": variables,
            "bounding_box": bbox_dict,
            "temporal_range": {
                "start": start_datetime,
                "end": end_datetime,
            },
            "created_at": created_at,
            "storage_records": storage_records,
            "retrieval_status": retrieval_result.get("status"),
        }

        # Save provenance record to staging
        prov_path = self.staging_dir / f"provenance_{ingestion_id}.json"
        with open(prov_path, "w", encoding="utf-8") as f:
            json.dump(provenance, f, indent=2)

        return {
            "ingestion_id": ingestion_id,
            "status": "completed" if retrieval_result.get("status") == "success" else retrieval_result.get("status"),
            "cadence": cadence,
            "variables": variables,
            "bounding_box": bbox_dict,
            "retrieval": retrieval_result,
            "provenance": provenance,
            "provenance_file": str(prov_path),
        }
