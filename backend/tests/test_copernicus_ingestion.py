"""
Comprehensive unit and integration test suite for Copernicus NRT and Historical Ingestion.

Distinguishes mocked tests from live Copernicus retrieval.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import numpy as np

from app.main import app
from app.modules.data_sources.copernicus.constants import (
    DEFAULT_INDIAN_OCEAN_BOUNDS,
    DATASET_HISTORICAL_DAILY,
    DATASET_NRT_DAILY_THETAO,
    DATASET_NRT_DAILY_SO,
    DATASET_NRT_DAILY_CURRENTS,
    DATASET_NRT_SIX_HOURLY_THETAO,
    DATASET_NRT_SIX_HOURLY_SO,
    DATASET_NRT_SIX_HOURLY_CURRENTS,
)
from app.modules.data_sources.copernicus.service import (
    plan_retrieval,
    get_verified_datasets,
    retrieve_copernicus_subset,
)
from app.modules.ingestion.copernicus_ingestion import (
    CopernicusIngestionPipeline,
    compute_sha256,
)
from app.modules.validation.marine_validator import (
    BoundingBox,
    validate_cadence,
    validate_variables,
    validate_ocean_array,
)


class TestCopernicusValidation(unittest.TestCase):
    """Unit tests for spatial bounds, variables, and physical limits validation."""

    def test_default_indian_ocean_bounds(self):
        bbox = BoundingBox.default_indian_ocean()
        self.assertEqual(bbox.minimum_longitude, 30.0)
        self.assertEqual(bbox.maximum_longitude, 120.0)
        self.assertEqual(bbox.minimum_latitude, -30.0)
        self.assertEqual(bbox.maximum_latitude, 30.0)
        bbox.validate()  # Should not raise

    def test_invalid_longitude_bounds(self):
        bbox = BoundingBox(minimum_longitude=130.0, maximum_longitude=120.0, minimum_latitude=-10.0, maximum_latitude=10.0)
        with self.assertRaises(ValueError):
            bbox.validate()

    def test_out_of_range_latitude(self):
        bbox = BoundingBox(minimum_longitude=30.0, maximum_longitude=120.0, minimum_latitude=-95.0, maximum_latitude=30.0)
        with self.assertRaises(ValueError):
            bbox.validate()

    def test_cadence_validation(self):
        validate_cadence("nrt_six_hourly")
        validate_cadence("nrt_daily")
        validate_cadence("historical_daily")
        with self.assertRaises(ValueError):
            validate_cadence("invalid_cadence")

    def test_variable_validation(self):
        validate_variables(["thetao", "so"])
        validate_variables(["uo", "vo"])
        with self.assertRaises(ValueError):
            validate_variables([])
        with self.assertRaises(ValueError):
            validate_variables(["unknown_var"])

    def test_ocean_array_physical_limits(self):
        # Temperature valid
        temp_data = np.array([20.0, 22.5, 25.0, 28.0])
        res = validate_ocean_array("thetao", temp_data)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.valid_points, 4)
        self.assertEqual(res.nan_points, 0)
        self.assertAlmostEqual(res.min_observed, 20.0)
        self.assertAlmostEqual(res.max_observed, 28.0)

        # Salinity out of bounds (> 50 psu)
        sal_data = np.array([34.0, 35.5, 75.0])
        res_sal = validate_ocean_array("so", sal_data)
        self.assertFalse(res_sal.is_valid)
        self.assertEqual(res_sal.out_of_bounds_points, 1)

        # NaN handling (e.g. land mask)
        masked_data = np.array([25.0, np.nan, 26.0])
        res_masked = validate_ocean_array("thetao", masked_data)
        self.assertTrue(res_masked.is_valid)
        self.assertEqual(res_masked.valid_points, 2)
        self.assertEqual(res_masked.nan_points, 1)


class TestCopernicusRetrievalPlanning(unittest.TestCase):
    """Unit tests for dataset ID resolution and retrieval planning."""

    def test_nrt_daily_retrieval_plan(self):
        plan = plan_retrieval("nrt_daily", ["thetao", "so", "uo", "vo"])
        dataset_ids = {p["dataset_id"] for p in plan}
        self.assertIn(DATASET_NRT_DAILY_THETAO, dataset_ids)
        self.assertIn(DATASET_NRT_DAILY_SO, dataset_ids)
        self.assertIn(DATASET_NRT_DAILY_CURRENTS, dataset_ids)

    def test_nrt_six_hourly_retrieval_plan(self):
        plan = plan_retrieval("nrt_six_hourly", ["thetao", "uo", "vo"])
        dataset_ids = {p["dataset_id"] for p in plan}
        self.assertIn(DATASET_NRT_SIX_HOURLY_THETAO, dataset_ids)
        self.assertIn(DATASET_NRT_SIX_HOURLY_CURRENTS, dataset_ids)

    def test_historical_daily_retrieval_plan(self):
        plan = plan_retrieval("historical_daily", ["thetao", "so", "uo", "vo"])
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["dataset_id"], DATASET_HISTORICAL_DAILY)
        self.assertEqual(set(plan[0]["variables"]), {"thetao", "so", "uo", "vo"})


class TestCopernicusIngestionPipeline(unittest.TestCase):
    """Unit tests for ingestion workflow, provenance, and storage integration."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.staging_dir = Path(self.test_dir.name)
        self.pipeline = CopernicusIngestionPipeline(staging_dir=self.staging_dir)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_sha256_computation(self):
        dummy_file = self.staging_dir / "test_data.bin"
        dummy_file.write_bytes(b"Copernicus Marine Test Data Stream")
        checksum = compute_sha256(dummy_file)
        self.assertEqual(len(checksum), 64)

    @patch("app.modules.ingestion.copernicus_ingestion.retrieve_copernicus_subset")
    @patch("app.modules.ingestion.copernicus_ingestion.s3_client")
    def test_pipeline_execution_with_mocked_retrieval(self, mock_s3, mock_subset):
        # Create a mock downloaded file
        mock_nc = self.staging_dir / "cmems_mock_thetao.nc"
        mock_nc.write_bytes(b"CDF\x02mock_netcdf_content_thetao")

        mock_subset.return_value = {
            "status": "success",
            "cadence": "nrt_daily",
            "variables": ["thetao"],
            "downloaded_files": [
                {
                    "dataset_id": DATASET_NRT_DAILY_THETAO,
                    "variables": ["thetao"],
                    "status": "success",
                    "response": str(mock_nc),
                }
            ],
        }

        result = self.pipeline.run_ingestion(
            cadence="nrt_daily",
            variables=["thetao"],
            bounding_box=BoundingBox.default_indian_ocean(),
        )

        self.assertEqual(result["status"], "completed")
        self.assertIn("ingestion_id", result)
        self.assertIn("provenance", result)

        prov = result["provenance"]
        self.assertEqual(prov["provider"], "Copernicus Marine Service")
        self.assertEqual(prov["cadence"], "nrt_daily")
        self.assertEqual(len(prov["storage_records"]), 1)
        self.assertEqual(prov["storage_records"][0]["sha256"], compute_sha256(mock_nc))
        self.assertTrue(Path(result["provenance_file"]).exists())

    def test_pipeline_authentication_required_when_unconfigured(self):
        # When neither env nor params provide credentials
        with patch("app.modules.data_sources.copernicus.service.settings.copernicus_marine_username", None), \
             patch("app.modules.data_sources.copernicus.service.settings.copernicus_marine_password", None):
            result = self.pipeline.run_ingestion(
                cadence="nrt_daily",
                variables=["thetao"],
                dry_run=False,
            )
            self.assertEqual(result["status"], "authentication_required")
            self.assertIn("Copernicus Marine Service requires free account credentials", result["message"])


class TestCopernicusApiRoutes(unittest.TestCase):
    """Tests for FastAPI Copernicus routes."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_get_verified_datasets_endpoint(self):
        response = self.client.get("/api/v1/data-sources/copernicus/datasets")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["provider"], "Copernicus Marine Service")
        self.assertEqual(data["target_region"], "Indian Ocean")
        self.assertIn("nrt_six_hourly", data["cadences"])
        self.assertIn("nrt_daily", data["cadences"])
        self.assertIn("historical_daily", data["cadences"])

    def test_get_region_endpoint(self):
        response = self.client.get("/api/v1/data-sources/copernicus/region")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["region_name"], "Indian Ocean")
        self.assertEqual(data["bounds"]["minimum_longitude"], 30.0)
        self.assertEqual(data["bounds"]["maximum_longitude"], 120.0)
        self.assertEqual(data["bounds"]["minimum_latitude"], -30.0)
        self.assertEqual(data["bounds"]["maximum_latitude"], 30.0)

    def test_validate_parameters_endpoint_valid(self):
        payload = {
            "cadence": "nrt_daily",
            "variables": ["thetao", "so"],
            "minimum_longitude": 40.0,
            "maximum_longitude": 100.0,
            "minimum_latitude": -20.0,
            "maximum_latitude": 20.0,
        }
        response = self.client.post("/api/v1/data-sources/copernicus/validate", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_valid"])
        self.assertEqual(len(data["errors"]), 0)

    def test_validate_parameters_endpoint_invalid(self):
        payload = {
            "cadence": "invalid_cadence",
            "variables": ["invalid_var"],
            "minimum_longitude": 150.0,
            "maximum_longitude": 100.0,  # min > max
            "minimum_latitude": -100.0,  # lat < -90
            "maximum_latitude": 20.0,
        }
        response = self.client.post("/api/v1/data-sources/copernicus/validate", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["is_valid"])
        self.assertGreaterEqual(len(data["errors"]), 3)


if __name__ == "__main__":
    unittest.main()
