"""
Unit and Integration Tests for Central Scientific Dataset Catalogue and Lifecycle.
"""

import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import get_db
from app.database.models import Base, ScientificCatalogEntryModel
from app.modules.catalogue.service import CentralCatalogueService
from app.main import app


class TestCentralCatalogue(unittest.TestCase):
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
        self.service = CentralCatalogueService()

    def tearDown(self):
        self.db.close()

    def test_seed_and_list_datasets(self):
        # 1. Seed standard catalogue
        count = self.service.seed_catalogue(self.db)
        self.assertGreaterEqual(count, 10)

        # 2. List all
        all_ds = self.service.list_datasets(self.db)
        self.assertGreaterEqual(all_ds["total"], 10)

        # 3. Filter by provider 'copernicus'
        cop_ds = self.service.list_datasets(self.db, provider_id="copernicus")
        self.assertGreaterEqual(cop_ds["total"], 2)

        # 4. Filter by variable 'sst'
        sst_ds = self.service.list_datasets(self.db, variable="sst")
        self.assertGreaterEqual(sst_ds["total"], 1)

    def test_get_dataset_and_lifecycle_update(self):
        self.service.seed_catalogue(self.db)

        # 1. Get single
        entry = self.service.get_dataset(self.db, "noaa-oisst-v2")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["provider_id"], "noaa")
        self.assertEqual(entry["verification_lifecycle_status"], "production_approved")

        # 2. Update lifecycle
        updated = self.service.update_lifecycle(
            self.db,
            "noaa-oisst-v2",
            "sample_validated",
            quality_notes="Subset download verified against NOAA server.",
        )
        self.assertEqual(updated["verification_lifecycle_status"], "sample_validated")

        # 3. Invalid status should raise ValueError
        with self.assertRaises(ValueError):
            self.service.update_lifecycle(self.db, "noaa-oisst-v2", "invalid_status_xyz")

    def test_api_routes(self):
        # 1. API Seed
        resp_seed = self.client.post("/api/v1/catalogue/seed")
        self.assertEqual(resp_seed.status_code, 201)

        # 2. API List
        resp_list = self.client.get("/api/v1/catalogue/datasets?provider_id=argo")
        self.assertEqual(resp_list.status_code, 200)
        data = resp_list.json()
        self.assertGreaterEqual(data["total"], 1)

        # 3. API Summary
        resp_sum = self.client.get("/api/v1/catalogue/summary")
        self.assertEqual(resp_sum.status_code, 200)
        sum_data = resp_sum.json()
        self.assertIn("providers_count", sum_data)
        self.assertGreaterEqual(sum_data["providers_count"], 5)

        # 4. API Patch Lifecycle
        patch_payload = {
            "status": "access_tested",
            "quality_notes": "Tested endpoint via API test",
        }
        resp_patch = self.client.patch("/api/v1/catalogue/datasets/argo-gdac-profiles/lifecycle", json=patch_payload)
        self.assertEqual(resp_patch.status_code, 200)
        patch_data = resp_patch.json()
        self.assertEqual(patch_data["dataset"]["verification_lifecycle_status"], "access_tested")


if __name__ == "__main__":
    unittest.main()
