import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.modules.data_sources.copernicus.service import search_catalogue


class TestMarineApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("project", data)
        self.assertEqual(data["message"], "Marine AI Platform API is running")
        self.assertEqual(data["version"], "0.1.0")

    @patch("app.main.test_storage_connection")
    @patch("app.main.engine.connect")
    def test_health_check_endpoint(self, mock_db, mock_storage):
        mock_db.return_value.__enter__.return_value.execute.return_value = True
        mock_storage.return_value = ["marine-raw"]
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("services", data)
        self.assertEqual(data["services"]["postgresql"], "healthy")
        self.assertEqual(data["services"]["seaweedfs"], "healthy")

    def test_copernicus_search_validation_missing_keyword(self):
        response = self.client.get("/api/v1/data-sources/copernicus/search")
        self.assertEqual(response.status_code, 422)

    def test_copernicus_search_validation_short_keyword(self):
        response = self.client.get("/api/v1/data-sources/copernicus/search?keyword=a")
        self.assertEqual(response.status_code, 422)

    @patch("app.modules.data_sources.copernicus.service.copernicusmarine.describe")
    def test_copernicus_search_service_mocked(self, mock_describe):
        mock_product = MagicMock()
        mock_product.product_id = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
        mock_product.title = "Global Ocean Physics Reanalysis"

        mock_result = MagicMock()
        mock_result.products = [mock_product]
        mock_describe.return_value = mock_result

        result = search_catalogue(keyword="salinity", limit=5)
        self.assertEqual(result["provider"], "Copernicus Marine")
        self.assertEqual(result["query"], "salinity")
        self.assertEqual(result["total_found"], 1)
        self.assertEqual(result["returned"], 1)
        self.assertEqual(len(result["products"]), 1)
        self.assertEqual(result["products"][0]["product_id"], "cmems_mod_glo_phy_my_0.083deg_P1D-m")


if __name__ == "__main__":
    unittest.main()
