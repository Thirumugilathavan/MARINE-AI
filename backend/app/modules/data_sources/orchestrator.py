"""
Unified Ingestion Orchestrator for Multi-Provider Marine Data Operations.

Coordinates parameter validation, dry-run previews, bounded retrievals,
scientific validation, S3 retention (SeaweedFS), and database persistence
across all registered marine data providers (Copernicus, NOAA, Argo, INCOIS).
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.database.models import (
    IngestionJobModel,
    IngestionAssetModel,
    ValidationReportModel,
    ProvenanceRecordModel,
    utc_now,
)
from app.storage.s3_client import s3_client
from app.modules.data_sources.base import (
    UnifiedRetrievalParams,
    UnifiedPreviewResult,
    UnifiedRetrievalResult,
    UnifiedValidationResult,
    UnifiedProvenanceInfo,
)
from app.modules.data_sources.registry import provider_registry
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    RetrievalError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class UnifiedIngestionOrchestrator:
    """
    Unified multi-provider ingestion orchestrator.
    """

    def preview_ingestion(self, params: UnifiedRetrievalParams) -> UnifiedPreviewResult:
        """Executes a dry-run / preview without downloading data."""
        provider = provider_registry.get(params.provider_id)
        return provider.preview(params)

    def create_ingestion_job(
        self,
        params: UnifiedRetrievalParams,
        db: Session,
        retain_in_s3: bool = False,
    ) -> IngestionJobModel:
        """
        Creates an IngestionJob record in the database in 'pending' status.
        """
        provider = provider_registry.get(params.provider_id)
        dataset_meta = provider.get_dataset(params.dataset_id)

        job_id = f"{params.provider_id}-job-{uuid.uuid4().hex[:12]}"
        job = IngestionJobModel(
            id=job_id,
            provider=provider.metadata().name,
            product_id=dataset_meta.product_id,
            dataset_id=params.dataset_id,
            dataset_version=params.dataset_version,
            dataset_part=params.dataset_part or "default",
            requested_variables=params.variables,
            requested_spatial_extent={
                "min_lon": params.minimum_longitude,
                "max_lon": params.maximum_longitude,
                "min_lat": params.minimum_latitude,
                "max_lat": params.maximum_latitude,
            },
            requested_time_interval={
                "start": params.start_datetime,
                "end": params.end_datetime,
            },
            requested_depth_interval={
                "min_depth": params.minimum_depth,
                "max_depth": params.maximum_depth,
            },
            request_parameters=params.to_dict(),
            status="pending",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info(f"Created ingestion job {job.id} for provider {params.provider_id}")
        return job

    def run_ingestion_job(
        self,
        job_id: str,
        params: UnifiedRetrievalParams,
        db: Session,
        retain_in_s3: bool = False,
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Executes end-to-end ingestion workflow for a job:
        1. Retrieval -> local staging
        2. Asset registration & SHA256 hashing
        3. Optional S3 persistence (SeaweedFS)
        4. Scientific NetCDF validation
        5. Provenance lineage recording
        6. State transitions (pending -> running -> completed / failed)
        """
        job = db.scalar(select(IngestionJobModel).where(IngestionJobModel.id == job_id))
        if not job:
            raise ValueError(f"Job {job_id} not found in database.")

        provider = provider_registry.get(params.provider_id)
        dataset_meta = provider.get_dataset(params.dataset_id)

        # Transition to running
        job.status = "running"
        job.started_at = utc_now()
        db.commit()

        try:
            # 1. Retrieve data
            if output_dir is None:
                output_dir = Path("dataset-staging") / params.provider_id
            output_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Retrieving data for job {job_id} via {params.provider_id} provider...")
            retrieval_res: UnifiedRetrievalResult = provider.retrieve(
                params=params, job_id=job_id, staging_dir=output_dir
            )

            # 2. Register binary asset
            asset = IngestionAssetModel(
                id=str(uuid.uuid4()),
                job_id=job_id,
                filename=retrieval_res.file_path.name,
                file_format=retrieval_res.file_format,
                file_size_bytes=retrieval_res.file_size_bytes,
                sha256_checksum=retrieval_res.sha256_checksum,
                storage_backend="local_staging",
                local_staging_path=str(retrieval_res.file_path),
                validation_status="pending",
            )
            db.add(asset)
            db.commit()
            db.refresh(asset)

            # 3. Optional SeaweedFS S3 upload
            if retain_in_s3:
                bucket_name = "marine-raw"
                s3_key = f"{params.provider_id}/{params.dataset_id}/{retrieval_res.file_path.name}"
                try:
                    s3_client.upload_file(retrieval_res.file_path, bucket_name, s3_key)
                    asset.storage_backend = "seaweedfs_s3"
                    asset.storage_bucket = bucket_name
                    asset.storage_key = s3_key
                    db.commit()
                    logger.info(f"Persisted asset to SeaweedFS S3: {bucket_name}/{s3_key}")
                except Exception as s3_exc:
                    logger.warning(f"SeaweedFS retention skipped or failed: {s3_exc}")

            # 4. Scientific NetCDF Validation
            logger.info(f"Validating retrieved data asset for job {job_id}...")
            val_res: UnifiedValidationResult = provider.validate_data(
                retrieval_res.file_path, params=params
            )

            # Format statistics dictionary
            val_stats = val_res.variable_stats or getattr(val_res, "variable_statistics", {}) or {}
            val_dims = val_res.dimensions or getattr(val_res, "actual_dimensions", {}) or {}

            var_stats_dict = {
                var_name: summary.to_dict() if hasattr(summary, "to_dict") else summary
                for var_name, summary in val_stats.items()
            }

            validation_report = ValidationReportModel(
                id=str(uuid.uuid4()),
                job_id=job_id,
                asset_id=asset.id,
                validation_status="passed" if val_res.is_valid and not val_res.warnings else (
                    "warnings" if val_res.is_valid else "failed"
                ),
                variables_validated=list(val_stats.keys()),
                dimensions=val_dims,
                coordinates_summary={
                    "spatial_extent": val_res.spatial_extent or val_res.coordinates_summary.get("spatial_extent", {}),
                    "temporal_extent": val_res.temporal_extent or val_res.coordinates_summary.get("temporal_extent", {}),
                    "coordinates_valid": getattr(val_res, "coordinates_valid", True),
                },
                valid_points_count=sum(getattr(s, "valid_points", 0) for s in val_stats.values()),
                missing_points_count=sum(getattr(s, "missing_points", 0) for s in val_stats.values()),
                invalid_points_count=sum(getattr(s, "out_of_range_points", 0) for s in val_stats.values()),
                statistics=var_stats_dict,
                cf_conventions=val_res.cf_conventions or "CF-1.8",
                warnings=val_res.warnings,
                errors=val_res.errors,
            )
            db.add(validation_report)

            # Update asset status
            asset.validation_status = validation_report.validation_status
            db.commit()

            # 5. Provenance Record
            prov_info: UnifiedProvenanceInfo = provider.generate_provenance(
                retrieval_res, val_res, params
            )

            units_dict = {
                v: dataset_meta.variable_metadata.get(v, {}).get("units", "unknown")
                for v in params.variables
            }

            provenance_record = ProvenanceRecordModel(
                id=str(uuid.uuid4()),
                job_id=job_id,
                provider=provider.metadata().name,
                product_id=dataset_meta.product_id,
                dataset_id=params.dataset_id,
                dataset_version=params.dataset_version,
                dataset_part=params.dataset_part,
                provider_doi=prov_info.citation,
                retrieval_timestamp=retrieval_res.retrieval_timestamp,
                requested_date_range={"start": params.start_datetime, "end": params.end_datetime},
                actual_data_date_range=val_res.temporal_extent,
                spatial_extent=val_res.spatial_extent,
                variables=params.variables,
                units=units_dict,
                processing_method=f"{params.provider_id}_retrieval_service",
                source_licence=dataset_meta.licence_information,
                toolbox_version="MARINE-AI-Unified-1.0",
                sha256_checksum=retrieval_res.sha256_checksum,
                validation_report_id=validation_report.id,
            )
            db.add(provenance_record)

            # Complete job
            job.status = "completed" if val_res.is_valid else "failed"
            if not val_res.is_valid:
                job.error_summary = "; ".join(val_res.errors)
            job.completed_at = utc_now()
            db.commit()
            db.refresh(job)

            return {
                "job_id": job.id,
                "status": job.status,
                "provider": params.provider_id,
                "dataset_id": params.dataset_id,
                "asset": {
                    "id": asset.id,
                    "filename": asset.filename,
                    "file_size_bytes": asset.file_size_bytes,
                    "sha256_checksum": asset.sha256_checksum,
                    "storage_backend": asset.storage_backend,
                },
                "validation": {
                    "id": validation_report.id,
                    "status": validation_report.validation_status,
                    "warnings": validation_report.warnings,
                    "errors": validation_report.errors,
                },
                "provenance": {
                    "id": provenance_record.id,
                    "sha256_checksum": provenance_record.sha256_checksum,
                },
            }

        except Exception as exc:
            logger.error(f"Ingestion job {job_id} failed: {exc}", exc_info=True)
            db.rollback()
            try:
                failed_job = db.scalar(select(IngestionJobModel).where(IngestionJobModel.id == job_id))
                if failed_job:
                    failed_job.status = "failed"
                    failed_job.error_summary = str(exc)
                    failed_job.completed_at = utc_now()
                    db.commit()
            except Exception as inner_exc:
                logger.warning(f"Could not persist failure status: {inner_exc}")
            raise

    # --------------------------------------------------------------------------
    # Database Query Functions
    # --------------------------------------------------------------------------
    def list_jobs(
        self,
        db: Session,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[IngestionJobModel]:
        stmt = select(IngestionJobModel).order_by(desc(IngestionJobModel.created_at))
        if provider:
            stmt = stmt.where(IngestionJobModel.provider.ilike(f"%{provider}%"))
        if status:
            stmt = stmt.where(IngestionJobModel.status == status)
        stmt = stmt.limit(limit).offset(offset)
        return list(db.scalars(stmt).all())

    def get_job(self, job_id: str, db: Session) -> Optional[IngestionJobModel]:
        return db.scalar(select(IngestionJobModel).where(IngestionJobModel.id == job_id))

    def get_job_assets(self, job_id: str, db: Session) -> List[IngestionAssetModel]:
        return list(db.scalars(select(IngestionAssetModel).where(IngestionAssetModel.job_id == job_id)).all())

    def get_job_validation(self, job_id: str, db: Session) -> List[ValidationReportModel]:
        return list(db.scalars(select(ValidationReportModel).where(ValidationReportModel.job_id == job_id)).all())

    def get_job_provenance(self, job_id: str, db: Session) -> List[ProvenanceRecordModel]:
        return list(db.scalars(select(ProvenanceRecordModel).where(ProvenanceRecordModel.job_id == job_id)).all())


# Global orchestrator singleton
unified_orchestrator = UnifiedIngestionOrchestrator()
