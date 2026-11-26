"""
Unit and Integration Tests for WoRMS Marine Species Taxonomy Service and API.
"""

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import get_db
from app.database.models import Base, MarineTaxonModel, TaxonomyLookupCacheModel
from app.modules.data_sources.worms.service import WoRMSTaxonomyService
from app.main import app


class TestWoRMSTaxonomy(unittest.TestCase):
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
        self.service = WoRMSTaxonomyService()

    def tearDown(self):
        self.db.close()

    @patch("app.modules.data_sources.worms.service.httpx.Client")
    def test_lookup_by_name_and_cache(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "AphiaID": 127027,
                "scientificname": "Thunnus albacares",
                "authority": "(Bonnaterre, 1788)",
                "rank": "Species",
                "status": "accepted",
                "valid_AphiaID": 127027,
                "valid_name": "Thunnus albacares",
                "kingdom": "Animalia",
                "phylum": "Chordata",
                "class": "Teleostei",
                "order": "Scombriformes",
                "family": "Scombridae",
                "genus": "Thunnus",
                "citation": "WoRMS (2025)",
                "lsid": "urn:lsid:marinespecies.org:taxname:127027",
                "url": "https://www.marinespecies.org/aphia.php?p=taxdetails&id=127027",
                "isMarine": 1,
            }
        ]
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        # 1. First lookup triggers HTTP request
        results = self.service.lookup_by_name("Thunnus albacares", db=self.db)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["aphia_id"], 127027)
        self.assertEqual(results[0]["scientific_name"], "Thunnus albacares")

        # Verify DB insertion
        cached_taxon = self.db.query(MarineTaxonModel).filter_by(aphia_id=127027).first()
        self.assertIsNotNone(cached_taxon)
        self.assertEqual(cached_taxon.family, "Scombridae")

        # 2. Second lookup should hit cache without new HTTP call
        mock_client.get.reset_mock()
        cached_results = self.service.lookup_by_name("Thunnus albacares", db=self.db)
        self.assertEqual(len(cached_results), 1)
        self.assertEqual(cached_results[0]["aphia_id"], 127027)
        mock_client.get.assert_not_called()

    @patch("app.modules.data_sources.worms.service.httpx.Client")
    def test_get_by_aphia_id(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "AphiaID": 126436,
            "scientificname": "Balaenoptera musculus",
            "authority": "(Linnaeus, 1758)",
            "rank": "Species",
            "status": "accepted",
            "valid_AphiaID": 126436,
            "valid_name": "Balaenoptera musculus",
            "kingdom": "Animalia",
            "phylum": "Chordata",
            "class": "Mammalia",
            "order": "Cetartiodactyla",
            "family": "Balaenopteridae",
            "genus": "Balaenoptera",
            "isMarine": 1,
        }
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        taxon = self.service.get_by_aphia_id(126436, db=self.db)
        self.assertIsNotNone(taxon)
        self.assertEqual(taxon["scientific_name"], "Balaenoptera musculus")
        self.assertEqual(taxon["class_name"], "Mammalia")

    @patch("app.modules.data_sources.worms.service.httpx.Client")
    def test_get_classification_and_synonyms(self, mock_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "AphiaID": 127027,
            "scientificname": "Thunnus albacares",
            "rank": "Species",
            "child": None,
        }
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        classification = self.service.get_classification(127027)
        self.assertIsNotNone(classification)
        self.assertEqual(classification["AphiaID"], 127027)

        # Synonyms mock
        mock_resp.json.return_value = [
            {
                "AphiaID": 273618,
                "scientificname": "Neothunnus albacares",
                "authority": "(Bonnaterre, 1788)",
                "status": "unaccepted",
            }
        ]
        synonyms = self.service.get_synonyms(127027, db=self.db)
        self.assertEqual(len(synonyms), 1)
        self.assertEqual(synonyms[0]["synonym_name"], "Neothunnus albacares")

    @patch("app.modules.data_sources.worms.service.worms_service.lookup_by_name")
    def test_api_endpoints(self, mock_lookup):
        mock_lookup.return_value = [
            {
                "aphia_id": 127027,
                "scientific_name": "Thunnus albacares",
                "authority": "(Bonnaterre, 1788)",
                "rank": "Species",
                "status": "accepted",
                "valid_aphia_id": 127027,
                "valid_name": "Thunnus albacares",
                "kingdom": "Animalia",
                "phylum": "Chordata",
                "class_name": "Teleostei",
                "order_name": "Scombriformes",
                "family": "Scombridae",
                "genus": "Thunnus",
                "is_marine": True,
            }
        ]

        # 1. API Lookup
        res = self.client.get("/api/v1/taxonomy/worms/lookup/Thunnus albacares")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["aphia_id"], 127027)

        # 2. API Taxa list
        res_list = self.client.get("/api/v1/taxonomy/taxa?family=Scombridae")
        self.assertEqual(res_list.status_code, 200)
        list_data = res_list.json()
        self.assertIn("total", list_data)


if __name__ == "__main__":
    unittest.main()
