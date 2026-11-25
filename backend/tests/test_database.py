"""
Database persistence tests for Copernicus Ingestion models using SQLite in-memory.
"""

from datetime import datetime, timezone
import unittest
import uuid
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    DatasetRegistryModel,
    IngestionJobModel,
    IngestionAssetModel,
    ValidationReportModel,
    ProvenanceRecordModel,
)


class TestDatabasePersistence(unittest.TestCase):

    def setUp(self):
        # Create an isolated SQLite in-memory database
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_tables_created(self):
        expected_tables = {
            "dataset_registry",
            "ingestion_jobs",
            "ingestion_assets",
            "validation_reports",
            "provenance_records",
        }
        self.assertTrue(expected_tables.issubset(set(Base.metadata.tables.keys())))

    def test_job_and_asset_lifecycle_persistence(self):
        job_id = str(uuid.uuid4())
        job = IngestionJobModel(
            id=job_id,
            provider="Copernicus Marine Service",
            product_id="GLOBAL_ANALYSISFORECAST_PHY_001_024",
            dataset_id="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
            dataset_version="202406",
            dataset_part="default",
            requested_variables=["thetao"],
            requested_spatial_extent={"min_lon": 85.0, "max_lon": 85.2, "min_lat": 12.0, "max_lat": 12.2},
            requested_time_interval={"start": "2026-11-20", "end": "2026-11-20"},
            requested_depth_interval={"min_depth": 0.49, "max_depth": 0.5},
            request_parameters={"retain_in_s3": True},
            status="queued",
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(job)
        self.session.commit()

        # Query back job
        retrieved_job = self.session.get(IngestionJobModel, job_id)
        self.assertIsNotNone(retrieved_job)
        self.assertEqual(retrieved_job.status, "queued")
        self.assertEqual(retrieved_job.dataset_id, "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m")

        # Add Asset
        asset_id = str(uuid.uuid4())
        asset = IngestionAssetModel(
            id=asset_id,
            job_id=job_id,
            filename="bay_of_bengal_thetao_test.nc",
            file_format="NetCDF-4",
            file_size_bytes=23846,
            sha256_checksum="abcdef1234567890",
            storage_backend="seaweedfs_s3",
            storage_bucket="marine-raw",
            storage_key=f"copernicus/thetao/{job_id}/bay_of_bengal_thetao_test.nc",
            validation_status="passed",
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(asset)

        # Add Validation Report
        report_id = str(uuid.uuid4())
        report = ValidationReportModel(
            id=report_id,
            job_id=job_id,
            asset_id=asset_id,
            validation_status="passed",
            variables_validated=["thetao"],
            dimensions={"time": 1, "depth": 1, "latitude": 3, "longitude": 3},
            coordinates_summary={"longitude": {"min": 85.0, "max": 85.17}},
            valid_points_count=9,
            missing_points_count=0,
            invalid_points_count=0,
            statistics={"thetao": {"min": 29.229, "max": 29.286, "mean": 29.264}},
            cf_conventions="CF-1.8",
            warnings=[],
            errors=[],
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(report)

        # Add Provenance Record
        prov_id = str(uuid.uuid4())
        prov = ProvenanceRecordModel(
            id=prov_id,
            job_id=job_id,
            provider="Copernicus Marine Service",
            product_id="GLOBAL_ANALYSISFORECAST_PHY_001_024",
            dataset_id="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
            dataset_version="202406",
            dataset_part="default",
            retrieval_timestamp=datetime.now(timezone.utc),
            requested_date_range={"start": "2026-11-20", "end": "2026-11-20"},
            actual_data_date_range={"start": "2026-11-20", "end": "2026-11-20"},
            spatial_extent={"lon": [85.0, 85.2], "lat": [12.0, 12.2]},
            variables=["thetao"],
            units={"thetao": "degrees_C"},
            processing_method="copernicusmarine_subset_api",
            toolbox_version="2.5.1",
            sha256_checksum="abcdef1234567890",
            validation_report_id=report_id,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(prov)

        # Update job to completed
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        self.session.commit()

        # Query job with relationships
        fresh_job = self.session.get(IngestionJobModel, job_id)
        self.assertEqual(fresh_job.status, "completed")
        self.assertEqual(len(fresh_job.assets), 1)
        self.assertEqual(fresh_job.assets[0].filename, "bay_of_bengal_thetao_test.nc")
        self.assertEqual(len(fresh_job.validation_reports), 1)
        self.assertEqual(fresh_job.validation_reports[0].valid_points_count, 9)
        self.assertEqual(len(fresh_job.provenance_records), 1)
        self.assertEqual(fresh_job.provenance_records[0].toolbox_version, "2.5.1")


if __name__ == "__main__":
    unittest.main()
