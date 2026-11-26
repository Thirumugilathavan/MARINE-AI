"""
Unit and Integration Tests for Scientific Research File Ingestion and Upload.
"""

import hashlib
import io
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.modules.research_files.upload_service import ResearchFileUploadService
from app.main import app


class TestResearchFiles(unittest.TestCase):
    def setUp(self):
        self.mock_storage = MagicMock()
        self.service = ResearchFileUploadService(storage=self.mock_storage)
        self.client = TestClient(app)

    def test_classify_file(self):
        # eDNA
        bucket, cat = self.service.classify_file("sample_R1.fastq.gz")
        self.assertEqual(bucket, "marine-edna")
        self.assertEqual(cat, "edna")

        bucket, cat = self.service.classify_file("marker_genes.fasta")
        self.assertEqual(bucket, "marine-edna")
        self.assertEqual(cat, "edna")

        # Media
        bucket, cat = self.service.classify_file("rov_dive_04.mp4")
        self.assertEqual(bucket, "marine-media")
        self.assertEqual(cat, "media")

        bucket, cat = self.service.classify_file("coral_transect.png")
        self.assertEqual(bucket, "marine-media")
        self.assertEqual(cat, "media")

        # Research / CTD / docs
        bucket, cat = self.service.classify_file("station_05.cnv")
        self.assertEqual(bucket, "marine-research")
        self.assertEqual(cat, "oceanography")

        bucket, cat = self.service.classify_file("cruise_report.pdf")
        self.assertEqual(bucket, "marine-research")
        self.assertEqual(cat, "documents")

    def test_compute_sha256_and_upload(self):
        content = b"TEST_SCIENTIFIC_DATA_STREAM"
        expected_sha = hashlib.sha256(content).hexdigest()

        res = self.service.upload_file(
            filename="station_profile.csv",
            file_bytes=content,
        )
        self.assertEqual(res["sha256_checksum"], expected_sha)
        self.assertEqual(res["file_size_bytes"], len(content))
        self.assertEqual(res["bucket_name"], "marine-research")
        self.assertEqual(res["category"], "oceanography")
        self.mock_storage.upload_fileobj.assert_called_once()

    @patch("app.modules.research_files.upload_service.upload_service.upload_file")
    def test_api_upload_endpoint(self, mock_upload):
        mock_upload.return_value = {
            "filename": "sequence.fastq.gz",
            "bucket_name": "marine-edna",
            "storage_key": "edna/2026/11/seq.fastq.gz",
            "category": "edna",
            "mime_type": "application/gzip",
            "file_size_bytes": 1024,
            "sha256_checksum": "abc123sha",
            "uploaded_at": "2026-11-26T10:00:00Z",
        }

        files = {"file": ("sequence.fastq.gz", b"MOCK_FASTQ_BYTES", "application/gzip")}
        resp = self.client.post("/api/v1/research-files/upload", files=files)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["file"]["bucket_name"], "marine-edna")


if __name__ == "__main__":
    unittest.main()
