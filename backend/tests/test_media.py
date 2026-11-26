"""
Unit and Integration Tests for Marine Image and Underwater Video Management.
"""

from datetime import datetime, timezone
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import get_db
from app.database.models import Base, MarineMediaAssetModel
from app.modules.media.service import MarineMediaService
from app.main import app


class TestMarineMedia(unittest.TestCase):
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
        self.service = MarineMediaService()

    def tearDown(self):
        self.db.close()

    @patch("app.modules.research_files.upload_service.upload_service.upload_file")
    def test_register_and_list_assets(self, mock_upload):
        mock_upload.return_value = {
            "filename": "rov_benthic_transect.mp4",
            "bucket_name": "marine-media",
            "storage_key": "media/2026/11/rov_benthic_transect.mp4",
            "category": "media",
            "mime_type": "video/mp4",
            "file_size_bytes": 1048576,
            "sha256_checksum": "hash123456",
            "uploaded_at": "2026-11-26T10:00:00Z",
        }

        asset = self.service.register_media_asset(
            db=self.db,
            project_id="PROJ-DEEP-REEF",
            filename="rov_benthic_transect.mp4",
            file_bytes=b"MOCK_VIDEO_DATA",
            mime_type="video/mp4",
            latitude=8.5,
            longitude=73.2,
            depth_meters=185.0,
            camera_sensor_info="4K UltraHD Submersible Camera",
            description="Deep benthic coral survey",
        )
        self.assertIsNotNone(asset.id)
        self.assertEqual(asset.bucket_name, "marine-media")
        self.assertEqual(asset.depth_meters, 185.0)

        # List assets
        res = self.service.list_assets(self.db, project_id="PROJ-DEEP-REEF")
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["assets"][0]["filename"], "rov_benthic_transect.mp4")

    @patch("app.modules.research_files.upload_service.upload_service.upload_file")
    def test_api_upload_and_get(self, mock_upload):
        mock_upload.return_value = {
            "filename": "whale_shark.jpg",
            "bucket_name": "marine-media",
            "storage_key": "media/2026/11/whale_shark.jpg",
            "category": "media",
            "mime_type": "image/jpeg",
            "file_size_bytes": 524288,
            "sha256_checksum": "sha_whale_shark",
            "uploaded_at": "2026-11-26T10:00:00Z",
        }

        files = {"file": ("whale_shark.jpg", b"MOCK_IMAGE_DATA", "image/jpeg")}
        data = {
            "project_id": "PROJ-PELAGIC-MEGAFAUNA",
            "latitude": 11.2,
            "longitude": 74.5,
            "depth_meters": 12.0,
        }
        resp = self.client.post("/api/v1/media/upload", files=files, data=data)
        self.assertEqual(resp.status_code, 201)
        asset_id = resp.json()["asset_id"]

        # Detail query
        resp_detail = self.client.get(f"/api/v1/media/assets/{asset_id}")
        self.assertEqual(resp_detail.status_code, 200)
        self.assertEqual(resp_detail.json()["project_id"], "PROJ-PELAGIC-MEGAFAUNA")


if __name__ == "__main__":
    unittest.main()
