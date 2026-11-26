"""
Unit and Integration Tests for eDNA Workflow and Taxonomic Assignments.
"""

from datetime import datetime, timezone
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import get_db
from app.database.models import Base, EDNASampleModel, EDNATaxonomicAssignmentModel
from app.modules.edna.service import EDNAWorkflowService, SAFEGUARD_NOTE
from app.main import app


class TestEDNAWorkflow(unittest.TestCase):
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
        self.service = EDNAWorkflowService()

    def tearDown(self):
        self.db.close()

    def test_create_sample_and_query(self):
        sample = self.service.create_sample(
            db=self.db,
            sample_code="IO-TEST-001",
            project_id="PROJ-ARABIAN-SEA",
            latitude=15.0,
            longitude=68.5,
            target_gene="12S",
            collected_at=datetime.now(timezone.utc),
            collection_depth_m=25.0,
            water_body="Arabian Sea",
            sequencing_platform="Illumina NovaSeq",
        )
        self.assertIsNotNone(sample.id)
        self.assertEqual(sample.sample_code, "IO-TEST-001")

        # Query list
        res = self.service.list_samples(self.db, project_id="PROJ-ARABIAN-SEA")
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["samples"][0]["sample_code"], "IO-TEST-001")

    @patch("app.modules.edna.service.worms_service.lookup_by_name")
    def test_add_taxonomic_assignment_with_worms(self, mock_worms):
        mock_worms.return_value = [{"aphia_id": 127027, "rank": "Species"}]

        # Create sample first
        sample = self.service.create_sample(
            db=self.db,
            sample_code="IO-TEST-002",
            project_id="PROJ-BAY-BENGAL",
            latitude=13.0,
            longitude=85.0,
            target_gene="12S",
            collected_at=datetime.now(timezone.utc),
        )

        assignment = self.service.add_taxonomic_assignment(
            db=self.db,
            sample_id=sample.id,
            asv_sequence_id="ASV_0042",
            matched_scientific_name="Thunnus albacares",
            read_count=1540,
            identity_percent=99.8,
            confidence_score=0.99,
            reference_database="MitoFish",
        )
        self.assertEqual(assignment.aphia_id, 127027)
        self.assertEqual(assignment.taxonomic_rank, "Species")
        self.assertEqual(assignment.scientific_interpretation_notes, SAFEGUARD_NOTE)

        # Retrieve details with assignment
        details = self.service.get_sample_details(self.db, sample.id)
        self.assertEqual(details["assignments_count"], 1)
        self.assertEqual(details["taxonomic_assignments"][0]["matched_scientific_name"], "Thunnus albacares")

    def test_api_sample_endpoints(self):
        payload = {
            "sample_code": "API-EDNA-001",
            "project_id": "SIH-EXP-2024",
            "latitude": 10.5,
            "longitude": 75.2,
            "target_gene": "COI",
            "collection_depth_m": 50.0,
        }
        res = self.client.post("/api/v1/edna/samples", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["sample_code"], "API-EDNA-001")

        # Query via API
        list_res = self.client.get("/api/v1/edna/samples?project_id=SIH-EXP-2024")
        self.assertEqual(list_res.status_code, 200)
        self.assertEqual(list_res.json()["total"], 1)


if __name__ == "__main__":
    unittest.main()
