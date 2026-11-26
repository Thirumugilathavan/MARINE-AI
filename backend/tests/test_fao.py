"""
Unit and Integration Tests for FAO Fisheries and Aquaculture Provider and API.
"""

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import get_db
from app.database.models import Base, FisheriesStatisticModel
from app.modules.data_sources.fao.service import FAOFisheriesProvider
from app.main import app


class TestFAOFisheries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        app.dependency_overrides.clear()

    def setUp(self):
        self.db = self.SessionLocal()
        self.provider = FAOFisheriesProvider()

    def tearDown(self):
        self.db.close()

    @patch("app.modules.data_sources.fao.service.httpx.Client")
    def test_get_major_areas(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "features": [
                {
                    "properties": {
                        "F_CODE": "51",
                        "NAME_EN": "Indian Ocean, Western",
                        "OCEAN": "Indian Ocean",
                    },
                    "geometry": None,
                },
                {
                    "properties": {
                        "F_CODE": "57",
                        "NAME_EN": "Indian Ocean, Eastern",
                        "OCEAN": "Indian Ocean",
                    },
                    "geometry": None,
                },
            ]
        }
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        areas = self.provider.get_major_areas()
        self.assertGreaterEqual(len(areas), 2)
        self.assertEqual(areas[0]["code"], "51")
        self.assertEqual(areas[0]["name"], "Indian Ocean, Western")

    def test_seed_and_query_baseline(self):
        # 1. Seed baseline records
        count = self.provider.seed_baseline_statistics(self.db)
        self.assertGreater(count, 0)

        # 2. Query statistics for India
        result = self.provider.query_statistics(
            self.db,
            country_iso3="IND",
            species_alpha3="YFT",
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["statistics"][0]["species_alpha3_code"], "YFT")
        self.assertEqual(result["statistics"][0]["country_name"], "India")

        # 3. Query summary via API
        resp = self.client.get("/api/v1/fisheries/summary?country_iso3=IND")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("summary", data)
        self.assertTrue(len(data["summary"]) > 0)

    def test_api_ingest(self):
        payload = {
            "records": [
                {
                    "country_iso3": "SYC",
                    "country_name": "Seychelles",
                    "fao_major_area": "Area 51 - Western Indian Ocean",
                    "species_scientific_name": "Thunnus obesus",
                    "species_common_name": "Bigeye tuna",
                    "species_alpha3_code": "BET",
                    "production_type": "capture",
                    "year": 2023,
                    "quantity_tonnes": 12500.0,
                }
            ]
        }
        resp = self.client.post("/api/v1/fisheries/ingest", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["ingested_count"], 1)

        # Verify query returns new record
        res_query = self.client.get("/api/v1/fisheries/statistics?country_iso3=SYC")
        self.assertEqual(res_query.status_code, 200)
        qdata = res_query.json()
        self.assertEqual(qdata["total"], 1)
        self.assertEqual(qdata["statistics"][0]["species_alpha3_code"], "BET")


if __name__ == "__main__":
    unittest.main()
