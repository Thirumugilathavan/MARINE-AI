"""
API endpoint tests for Copernicus Marine Data Ingestion module.
"""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.connection import get_db
from app.database.models import Base

FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "dataset-staging" / "copernicus-test" / "bay_of_bengal_thetao_test.nc"


class TestCopernicusAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def test_list_datasets(self):
        response = self.client.get("/api/v1/data-sources/copernicus/datasets")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        ds = data[0]
        self.assertEqual(ds["dataset_id"], "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m")
        self.assertEqual(ds["product_id"], "GLOBAL_ANALYSISFORECAST_PHY_001_024")
        self.assertIn("thetao", ds["available_variables"])

    def test_get_dataset_details_success(self):
        response = self.client.get("/api/v1/data-sources/copernicus/datasets/cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["dataset_id"], "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m")
        self.assertEqual(data["verification_status"], "verified")
        self.assertEqual(data["depth_levels_count"], 50)

    def test_get_dataset_details_not_found(self):
        response = self.client.get("/api/v1/data-sources/copernicus/datasets/unregistered_dataset_xyz")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not in the verified dataset registry", response.json()["detail"])

    @patch("app.modules.data_sources.copernicus.retrieval.copernicusmarine.subset")
    def test_preview_endpoint(self, mock_subset):
        mock_res = MagicMock()
        mock_res.file_size = 0.013
        mock_res.data_transfer_size = 2.09
        mock_res.message = "Dry-run preview succeeded"
        mock_ext = MagicMock()
        mock_ext.coordinate_id = "longitude"
        mock_ext.minimum = 85.0
        mock_ext.maximum = 85.17
        mock_ext.unit = "degrees_east"
        mock_response_extent = [mock_ext]
        mock_res.coordinates_extent = mock_response_extent
        mock_subset.return_value = mock_res

        payload = {
            "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
            "variables": ["thetao"],
            "minimum_longitude": 85.0,
            "maximum_longitude": 85.2,
            "minimum_latitude": 12.0,
            "maximum_latitude": 12.2,
            "start_datetime": "2026-11-20",
            "end_datetime": "2026-11-20",
            "minimum_depth": 0.49,
            "maximum_depth": 0.5,
        }

        response = self.client.post("/api/v1/data-sources/copernicus/preview", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("request_id", data)
        self.assertEqual(data["dataset_id"], "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m")
        self.assertEqual(data["estimated_file_size_mb"], 0.013)
        self.assertEqual(data["dry_run_status"], "success")

    def test_preview_invalid_bounds(self):
        payload = {
            "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
            "variables": ["thetao"],
            "minimum_longitude": 90.0,
            "maximum_longitude": 80.0,  # min > max
            "minimum_latitude": 12.0,
            "maximum_latitude": 12.2,
            "start_datetime": "2026-11-20",
            "end_datetime": "2026-11-20",
        }
        response = self.client.post("/api/v1/data-sources/copernicus/preview", json=payload)
        self.assertEqual(response.status_code, 400)

    @patch("app.modules.data_sources.copernicus.service.retrieval_service.execute_retrieval")
    def test_create_ingestion_synchronous(self, mock_exec):
        if FIXTURE_PATH.exists():
            mock_exec.return_value = FIXTURE_PATH
        else:
            # Create a mock path
            mock_file = Path("test_temp.nc")
            mock_exec.return_value = mock_file

        payload = {
            "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
            "variables": ["thetao"],
            "minimum_longitude": 85.0,
            "maximum_longitude": 85.2,
            "minimum_latitude": 12.0,
            "maximum_latitude": 12.2,
            "start_datetime": "2026-11-20",
            "end_datetime": "2026-11-20",
            "minimum_depth": 0.49,
            "maximum_depth": 0.5,
            "retain_in_s3": False,
        }

        response = self.client.post(
            "/api/v1/data-sources/copernicus/ingestions?run_synchronously=true",
            json=payload,
        )
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertIn("job_id", data)
        self.assertIn(data["status"], ["completed", "failed"])

        job_id = data["job_id"]

        # Check job status endpoint
        status_res = self.client.get(f"/api/v1/data-sources/copernicus/ingestions/{job_id}")
        self.assertEqual(status_res.status_code, 200)
        status_data = status_res.json()
        self.assertEqual(status_data["id"], job_id)

    def test_list_ingestions(self):
        response = self.client.get("/api/v1/data-sources/copernicus/ingestions")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_nonexistent_job(self):
        response = self.client.get("/api/v1/data-sources/copernicus/ingestions/non-existent-uuid")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
