"""
Comprehensive API Validation, Boundary Constraints, and Infrastructure Recovery Tests.

Tests:
1. Copernicus Search Validation:
   - Missing required keyword -> 422
   - Short keyword (< 2 characters) -> 422
   - Whitespace-only keyword -> 422
   - Limit below minimum (< 1) -> 422
   - Limit above maximum (> 50) -> 422
   - Valid keyword search (mocked and schema verified) -> 200
2. Unified Provider Search:
   - NOAA search with valid query -> 200
   - Argo search with valid query -> 200
   - INCOIS search with valid query -> 200
   - Copernicus search through unified route -> 200
   - Short query (< 2 characters) -> 422
   - Whitespace query -> 422
   - Unknown provider ID -> 404
3. Coordinate and Dimension Boundaries:
   - min_lon > max_lon -> 400/422
   - min_lat > max_lat -> 400/422
   - Out of range coordinates -> 422
4. Live Infrastructure Integration (Live PostgreSQL & SeaweedFS):
   - Health check endpoint -> 200
   - OpenAPI schema generation -> 200
   - Catalogue listing and response schema serialization -> 200
   - PostGIS spatial query validation -> 200
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.modules.data_sources.copernicus.schemas import CopernicusSearchResponseSchema
from app.modules.data_sources.registry import provider_registry


class TestApiValidationAndBoundaryConstraints(unittest.TestCase):
    """Unit tests for endpoint parameter validation and boundary enforcement."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    # --------------------------------------------------------------------------
    # 1. Copernicus Search Validation Tests
    # --------------------------------------------------------------------------
    def test_copernicus_search_missing_keyword_returns_422(self):
        """Omitting the required keyword parameter must yield HTTP 422 Unprocessable Entity."""
        res = self.client.get("/api/v1/data-sources/copernicus/search")
        self.assertEqual(res.status_code, 422)
        data = res.json()
        self.assertIn("detail", data)
        field_errors = [e.get("loc") for e in data["detail"]]
        self.assertTrue(any("keyword" in loc for loc in field_errors))

    def test_copernicus_search_short_keyword_returns_422(self):
        """Keywords under 2 characters must be rejected with 422."""
        res = self.client.get("/api/v1/data-sources/copernicus/search?keyword=a")
        self.assertEqual(res.status_code, 422)
        data = res.json()
        self.assertIn("detail", data)

    def test_copernicus_search_whitespace_keyword_returns_422(self):
        """Keywords composed solely of whitespace must be rejected with 422."""
        res = self.client.get("/api/v1/data-sources/copernicus/search?keyword=%20%20%20")
        self.assertEqual(res.status_code, 422)
        data = res.json()
        self.assertIn("detail", data)

    def test_copernicus_search_limit_below_min_returns_422(self):
        """Limit values less than 1 must be rejected with 422."""
        res = self.client.get("/api/v1/data-sources/copernicus/search?keyword=thetao&limit=0")
        self.assertEqual(res.status_code, 422)
        data = res.json()
        self.assertIn("detail", data)

    def test_copernicus_search_limit_above_max_returns_422(self):
        """Limit values exceeding 50 must be rejected with 422."""
        res = self.client.get("/api/v1/data-sources/copernicus/search?keyword=thetao&limit=51")
        self.assertEqual(res.status_code, 422)
        data = res.json()
        self.assertIn("detail", data)

    @patch("app.modules.data_sources.copernicus.service.copernicusmarine.describe")
    def test_copernicus_search_valid_keyword_returns_schema(self, mock_describe):
        """Valid query must return 200 and conform strictly to CopernicusSearchResponseSchema."""
        mock_prod = MagicMock()
        mock_prod.product_id = "cmems_mod_glo_phy_anfc_0.083deg_P1D-m"
        mock_prod.title = "Global Ocean Physics Analysis and Forecast"

        mock_res = MagicMock()
        mock_res.products = [mock_prod]
        mock_describe.return_value = mock_res

        res = self.client.get("/api/v1/data-sources/copernicus/search?keyword=thetao&limit=10")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Validate with Pydantic model
        schema_obj = CopernicusSearchResponseSchema(**data)
        self.assertEqual(schema_obj.provider, "Copernicus Marine")
        self.assertEqual(schema_obj.query, "thetao")
        self.assertEqual(schema_obj.returned, 1)
        self.assertEqual(len(schema_obj.products), 1)
        self.assertEqual(schema_obj.products[0].product_id, "cmems_mod_glo_phy_anfc_0.083deg_P1D-m")

    # --------------------------------------------------------------------------
    # 2. Unified Provider Search Validation Tests
    # --------------------------------------------------------------------------
    def test_unified_search_short_query_returns_422(self):
        """Short search queries on provider search must return 422."""
        res = self.client.get("/api/v1/providers/noaa/search?query=x")
        self.assertEqual(res.status_code, 422)

    def test_unified_search_whitespace_query_returns_422(self):
        """Whitespace queries on provider search must return 422."""
        res = self.client.get("/api/v1/providers/noaa/search?query=%20%20%20")
        self.assertEqual(res.status_code, 422)

    def test_unified_search_limit_out_of_bounds_returns_422(self):
        """Limit values out of range [1, 50] must return 422."""
        res_low = self.client.get("/api/v1/providers/noaa/search?query=sst&limit=0")
        self.assertEqual(res_low.status_code, 422)

        res_high = self.client.get("/api/v1/providers/noaa/search?query=sst&limit=100")
        self.assertEqual(res_high.status_code, 422)

    def test_unified_search_unknown_provider_returns_404(self):
        """Searching an unregistered provider must return HTTP 404."""
        res = self.client.get("/api/v1/providers/nonexistent_provider/search?query=sst")
        self.assertEqual(res.status_code, 404)

    def test_unified_search_argo_returns_200(self):
        """Argo provider search returns valid search response."""
        res = self.client.get("/api/v1/providers/argo/search?query=float&limit=5")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["provider_id"], "argo")
        self.assertIn("results", data)

    def test_unified_search_incois_returns_200(self):
        """INCOIS provider search returns valid search response."""
        res = self.client.get("/api/v1/providers/incois/search?query=wave&limit=5")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["provider_id"], "incois")
        self.assertIn("results", data)

    # --------------------------------------------------------------------------
    # 3. Coordinate and Dimension Boundary Constraints
    # --------------------------------------------------------------------------
    def test_bathymetry_depth_invalid_latitude_returns_422(self):
        """Latitude values outside [-90, 90] must return 422."""
        res = self.client.get("/api/v1/bathymetry/depth?longitude=70.0&latitude=95.0")
        self.assertEqual(res.status_code, 422)

    def test_bathymetry_depth_invalid_longitude_returns_422(self):
        """Longitude values outside [-180, 180] must return 422."""
        res = self.client.get("/api/v1/bathymetry/depth?longitude=190.0&latitude=15.0")
        self.assertEqual(res.status_code, 422)

    def test_copernicus_preview_inverted_longitude_returns_400(self):
        """Inverted longitude bounds (min > max) must return HTTP 400."""
        payload = {
            "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
            "variables": ["thetao"],
            "minimum_longitude": 85.5,
            "maximum_longitude": 85.0,  # Inverted
            "minimum_latitude": 12.0,
            "maximum_latitude": 12.2,
            "start_datetime": "2026-11-20",
            "end_datetime": "2026-11-20",
        }
        res = self.client.post("/api/v1/data-sources/copernicus/preview", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("minimum_longitude", res.json()["detail"])

    def test_unified_preview_inverted_bounds_returns_422(self):
        """Unified preview with inverted bounds returns HTTP 422."""
        payload = {
            "dataset_id": "ncdcOisst21Agg_LonPM180",
            "variables": ["sst"],
            "minimum_longitude": 70.0,
            "maximum_longitude": 60.0,  # Inverted
            "minimum_latitude": 15.0,
            "maximum_latitude": 16.0,
            "start_datetime": "2024-01-01T00:00:00Z",
            "end_datetime": "2024-01-02T00:00:00Z",
        }
        res = self.client.post("/api/v1/providers/noaa/preview", json=payload)
        self.assertEqual(res.status_code, 422)
        self.assertIn("minimum_longitude", res.json()["detail"])


class TestLiveInfrastructureIntegration(unittest.TestCase):
    """Integration tests connecting to live PostgreSQL, PostGIS, and SeaweedFS."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_live_health_endpoint(self):
        """Live /health check must confirm healthy PostgreSQL and SeaweedFS status."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["services"]["postgresql"], "healthy")
        self.assertEqual(data["services"]["seaweedfs"], "healthy")

    def test_live_openapi_generation(self):
        """OpenAPI 3.1 schema must generate cleanly with all tags and schemas."""
        res = self.client.get("/openapi.json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["info"]["title"], "Sstrix Marine AI Platform")
        self.assertIn("/api/v1/data-sources/copernicus/search", data["paths"])
        self.assertIn("/api/v1/catalogue/datasets", data["paths"])

    def test_live_catalogue_datasets_query(self):
        """Live catalogue returns registered scientific entries with full metadata."""
        res = self.client.get("/api/v1/catalogue/datasets?limit=5")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total"], 12)
        self.assertIn("datasets", data)
        self.assertTrue(len(data["datasets"]) > 0)

    def test_live_bathymetry_depth_lookup(self):
        """Live GEBCO bathymetry returns valid depth for Arabian Sea coordinates."""
        res = self.client.get("/api/v1/bathymetry/depth?longitude=70.0&latitude=15.0")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["longitude"], 70.0)
        self.assertEqual(data["latitude"], 15.0)
        self.assertTrue(data["is_ocean"])
        self.assertLess(data["elevation_m"], 0.0)

    def test_live_species_occurrences_query(self):
        """Live PostGIS occurrence search returns persisted species records."""
        res = self.client.get("/api/v1/biodiversity/occurrences/search?limit=3")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)


if __name__ == "__main__":
    unittest.main()
