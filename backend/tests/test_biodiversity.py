"""
Unit tests for OBIS and GBIF Biodiversity integrations and reconciliation.
"""

import unittest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.modules.data_sources.biodiversity.service import (
    OBISBiodiversityService,
    GBIFBiodiversityService,
    BiodiversityReconciliationEngine,
    haversine_distance_km,
)


class TestBiodiversityModule(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.engine = BiodiversityReconciliationEngine()

    def test_haversine_distance(self):
        # Known distance: London (0, 51.5) to Paris (2.35, 48.85) ~ 343 km
        dist = haversine_distance_km(0.0, 51.5, 2.35, 48.85)
        self.assertAlmostEqual(dist, 343.0, delta=10.0)

        # Zero distance
        self.assertEqual(haversine_distance_km(80.0, 12.0, 80.0, 12.0), 0.0)

    def test_obis_search_mocked(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total": 1,
            "results": [
                {
                    "id": "obis-test-1",
                    "scientificName": "Balaenoptera musculus",
                    "decimalLatitude": -10.5,
                    "decimalLongitude": 65.2,
                    "eventDate": "2023-05-12",
                    "aphiaID": 137090,
                    "datasetName": "Blue Whale Sightings",
                    "license": "CC-BY",
                }
            ],
        }

        service = OBISBiodiversityService()
        with patch("httpx.Client.get", return_value=mock_resp):
            recs = service.search_occurrences(scientific_name="Balaenoptera musculus")
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["provider"], "obis")
            self.assertEqual(recs[0]["scientific_name"], "Balaenoptera musculus")
            self.assertEqual(recs[0]["latitude"], -10.5)

    def test_gbif_search_mocked(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "count": 1,
            "results": [
                {
                    "key": 987654321,
                    "scientificName": "Balaenoptera musculus Linnaeus, 1758",
                    "decimalLatitude": -10.52,
                    "decimalLongitude": 65.21,
                    "year": 2023,
                    "basisOfRecord": "HUMAN_OBSERVATION",
                    "datasetName": "Marine Mammals Global",
                }
            ],
        }

        service = GBIFBiodiversityService()
        with patch("httpx.Client.get", return_value=mock_resp):
            recs = service.search_occurrences(scientific_name="Balaenoptera musculus")
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["provider"], "gbif")
            self.assertEqual(recs[0]["latitude"], -10.52)

    def test_api_occurrences_query_endpoint(self):
        mock_obis = [
            {
                "provider": "obis",
                "occurrence_id": "test-occ-1",
                "scientific_name": "Delphinus delphis",
                "latitude": 15.0,
                "longitude": 70.0,
            }
        ]
        with patch(
            "app.modules.data_sources.biodiversity.service.OBISBiodiversityService.search_occurrences",
            return_value=mock_obis,
        ):
            resp = self.client.post(
                "/api/v1/biodiversity/occurrences/query",
                json={"scientific_name": "Delphinus delphis", "provider": "obis"},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["total_returned"], 1)
            self.assertEqual(data["results"][0]["scientific_name"], "Delphinus delphis")


if __name__ == "__main__":
    unittest.main()
