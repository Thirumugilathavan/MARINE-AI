"""
Integration tests for Unified Multi-Provider API endpoints.
"""

import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.data_sources.registry import provider_registry


class TestUnifiedAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_list_providers(self):
        response = self.client.get("/api/v1/providers")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        p_ids = [p["provider_id"] for p in data]
        self.assertIn("copernicus", p_ids)
        self.assertIn("noaa", p_ids)
        self.assertIn("argo", p_ids)
        self.assertIn("incois", p_ids)

    def test_get_provider_details(self):
        for pid in ["copernicus", "noaa", "argo", "incois"]:
            response = self.client.get(f"/api/v1/providers/{pid}")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["provider_id"], pid)
            self.assertIn("name", data)
            self.assertIn("base_url", data)

    def test_get_unknown_provider(self):
        response = self.client.get("/api/v1/providers/unknown_provider_xyz")
        self.assertEqual(response.status_code, 404)

    def test_list_provider_datasets(self):
        # NOAA
        resp_noaa = self.client.get("/api/v1/providers/noaa/datasets")
        self.assertEqual(resp_noaa.status_code, 200)
        noaa_ds = resp_noaa.json()
        self.assertGreater(len(noaa_ds), 0)
        self.assertEqual(noaa_ds[0]["dataset_id"], "ncdcOisst21Agg_LonPM180")

        # Argo
        resp_argo = self.client.get("/api/v1/providers/argo/datasets")
        self.assertEqual(resp_argo.status_code, 200)
        argo_ds = resp_argo.json()
        self.assertGreater(len(argo_ds), 0)
        self.assertEqual(argo_ds[0]["dataset_id"], "ArgoFloats")

        # INCOIS
        resp_incois = self.client.get("/api/v1/providers/incois/datasets")
        self.assertEqual(resp_incois.status_code, 200)
        incois_ds = resp_incois.json()
        self.assertGreater(len(incois_ds), 0)
        self.assertEqual(incois_ds[0]["dataset_id"], "ascat_daily_datasets")

    def test_get_provider_dataset_details(self):
        response = self.client.get("/api/v1/providers/noaa/datasets/ncdcOisst21Agg_LonPM180")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["dataset_id"], "ncdcOisst21Agg_LonPM180")
        self.assertIn("sst", data["available_variables"])

    def test_preview_noaa_endpoint(self):
        payload = {
            "dataset_id": "ncdcOisst21Agg_LonPM180",
            "variables": ["sst"],
            "minimum_longitude": 65.0,
            "maximum_longitude": 75.0,
            "minimum_latitude": 10.0,
            "maximum_latitude": 20.0,
            "start_datetime": "2024-01-01T00:00:00Z",
            "end_datetime": "2024-01-03T00:00:00Z",
        }
        response = self.client.post("/api/v1/providers/noaa/preview", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["provider_id"], "noaa")
        self.assertIn(data["status"], ["valid", "success"])

    def test_preview_argo_endpoint(self):
        payload = {
            "dataset_id": "ArgoFloats",
            "variables": ["temp", "psal"],
            "minimum_longitude": 80.0,
            "maximum_longitude": 90.0,
            "minimum_latitude": 10.0,
            "maximum_latitude": 15.0,
            "start_datetime": "2024-01-01T00:00:00Z",
            "end_datetime": "2024-01-05T00:00:00Z",
        }
        response = self.client.post("/api/v1/providers/argo/preview", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["provider_id"], "argo")
        self.assertEqual(data["status"], "success")

    def test_preview_incois_endpoint(self):
        payload = {
            "dataset_id": "ascat_daily_datasets",
            "variables": ["wind_speed"],
            "minimum_longitude": 65.0,
            "maximum_longitude": 75.0,
            "minimum_latitude": 10.0,
            "maximum_latitude": 20.0,
            "start_datetime": "2024-01-01T00:00:00Z",
            "end_datetime": "2024-01-03T00:00:00Z",
        }
        response = self.client.post("/api/v1/providers/incois/preview", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["provider_id"], "incois")
        self.assertEqual(data["status"], "success")

    def test_list_ingestions(self):
        response = self.client.get("/api/v1/ingestions")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)


if __name__ == "__main__":
    unittest.main()
