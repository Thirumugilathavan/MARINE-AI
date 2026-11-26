"""
Unit tests for GEBCO Bathymetry Provider and API endpoints.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.modules.data_sources.base import UnifiedRetrievalParams
from app.modules.data_sources.gebco.service import gebco_provider, GEBCOBathymetryProvider
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
    InvalidBoundsError,
)


class TestGEBCOProvider(unittest.TestCase):
    def setUp(self):
        self.provider = GEBCOBathymetryProvider()
        self.client = TestClient(app)

    def test_metadata(self):
        meta = self.provider.metadata()
        self.assertEqual(meta.provider_id, "gebco")
        self.assertIn("Bathymetric Chart", meta.name)
        self.assertFalse(meta.authentication_required)

    def test_list_and_get_dataset(self):
        datasets = self.provider.list_datasets()
        self.assertGreaterEqual(len(datasets), 2)
        ds_ids = [d.dataset_id for d in datasets]
        self.assertIn("gebco_2024_grid", ds_ids)
        self.assertIn("gebco_sub_ice_topo", ds_ids)

        ds = self.provider.get_dataset("gebco_2024_grid")
        self.assertEqual(ds.dataset_id, "gebco_2024_grid")
        self.assertIn("elevation", ds.available_variables)

    def test_unknown_dataset(self):
        with self.assertRaises(DatasetNotFoundError):
            self.provider.get_dataset("nonexistent_bathymetry_grid")

    def test_validate_parameters_success(self):
        params = UnifiedRetrievalParams(
            provider_id="gebco",
            dataset_id="gebco_2024_grid",
            variables=["elevation", "depth"],
            minimum_longitude=65.0,
            maximum_longitude=70.0,
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-02T00:00:00Z",
        )
        validated = self.provider.validate_parameters(params)
        self.assertEqual(validated.dataset_id, "gebco_2024_grid")

    def test_validate_parameters_invalid_variable(self):
        params = UnifiedRetrievalParams(
            provider_id="gebco",
            dataset_id="gebco_2024_grid",
            variables=["salinity_invalid"],
            minimum_longitude=65.0,
            maximum_longitude=70.0,
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-02T00:00:00Z",
        )
        with self.assertRaises(InvalidVariableError):
            self.provider.validate_parameters(params)

    def test_validate_parameters_invalid_bounds(self):
        params = UnifiedRetrievalParams(
            provider_id="gebco",
            dataset_id="gebco_2024_grid",
            variables=["elevation"],
            minimum_longitude=75.0,
            maximum_longitude=70.0,  # min > max
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-02T00:00:00Z",
        )
        with self.assertRaises(InvalidBoundsError):
            self.provider.validate_parameters(params)

    def test_preview(self):
        params = UnifiedRetrievalParams(
            provider_id="gebco",
            dataset_id="gebco_2024_grid",
            variables=["elevation"],
            minimum_longitude=68.0,
            maximum_longitude=70.0,
            minimum_latitude=12.0,
            maximum_latitude=14.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-02T00:00:00Z",
        )
        prev = self.provider.preview(params)
        self.assertEqual(prev.status, "success")
        self.assertEqual(prev.bounding_box_area_deg2, 4.0)
        self.assertGreater(prev.estimated_total_points, 0)

    def test_point_depth_identify_mocked(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": "-3540.5",
            "location": {"x": 68.0, "y": 12.0},
        }

        with patch("httpx.Client.get", return_value=mock_response):
            res = self.provider.identify_point_depth(longitude=68.0, latitude=12.0)
            self.assertEqual(res["elevation_m"], -3540.5)
            self.assertEqual(res["water_depth_m"], 3540.5)
            self.assertTrue(res["is_ocean"])

    def test_api_bathymetry_endpoints(self):
        # 1. Depth endpoint
        with patch.object(
            gebco_provider,
            "identify_point_depth",
            return_value={
                "longitude": 68.0,
                "latitude": 12.0,
                "elevation_m": -4200.0,
                "water_depth_m": 4200.0,
                "is_ocean": True,
                "source": "GEBCO Mock",
                "crs": "EPSG:4326",
                "vertical_datum": "MSL",
            },
        ):
            resp = self.client.get("/api/v1/bathymetry/depth?longitude=68.0&latitude=12.0")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["water_depth_m"], 4200.0)
            self.assertTrue(data["is_ocean"])

        # 2. Profile endpoint
        with patch.object(
            gebco_provider,
            "identify_point_depth",
            return_value={
                "longitude": 68.0,
                "latitude": 12.0,
                "elevation_m": -4200.0,
                "water_depth_m": 4200.0,
                "is_ocean": True,
                "source": "GEBCO Mock",
                "crs": "EPSG:4326",
                "vertical_datum": "MSL",
            },
        ):
            resp2 = self.client.post(
                "/api/v1/bathymetry/profile",
                json={"coordinates": [[68.0, 12.0], [69.0, 13.0]]},
            )
            self.assertEqual(resp2.status_code, 200)
            self.assertEqual(len(resp2.json()), 2)


if __name__ == "__main__":
    unittest.main()
