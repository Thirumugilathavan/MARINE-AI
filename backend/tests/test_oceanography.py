"""
Unit and Integration Tests for Oceanographic CTD and ADCP Profile Parsers and API.
"""

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import get_db
from app.database.models import Base, OceanographicProfileModel, OceanographicObservationModel
from app.modules.oceanography.parsers import CTDParser, ADCPParser, OceanographyProfileService
from app.main import app


SAMPLE_CSV_CTD = """
depth_m,pressure_dbar,temperature_c,salinity_psu,conductivity_sm
1.0,1.01,28.45,35.12,5.42
10.0,10.08,28.12,35.15,5.39
25.0,25.20,26.50,35.30,5.25
50.0,50.40,22.10,35.45,4.80
100.0,100.80,18.25,35.20,4.40
"""

SAMPLE_SBE_CNV = """
* Sea-Bird SBE 9plus CTD Data File:
* System UpLoad Time = Nov 20 2024 10:15:00
# name 0 = prDM: Pressure, Digiquartz [db]
# name 1 = t090C: Temperature [ITS-90, deg C]
# name 2 = sal00: Salinity, Practical [PSU]
# name 3 = c0S/m: Conductivity [S/m]
*END*
      1.50     28.3201     35.1102      5.4120
     15.00     27.9500     35.1350      5.3850
     30.00     25.8000     35.2800      5.1800
"""

SAMPLE_ADCP_CSV = """
depth_m,velocity_u,velocity_v,velocity_w
5.0,0.35,0.42,-0.02
15.0,0.28,0.38,-0.01
25.0,0.15,0.25,0.00
35.0,0.08,0.12,0.01
"""


class TestOceanography(unittest.TestCase):
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
        self.service = OceanographyProfileService()

    def tearDown(self):
        self.db.query(OceanographicObservationModel).delete()
        self.db.query(OceanographicProfileModel).delete()
        self.db.commit()
        self.db.close()

    def test_parse_csv_ctd(self):
        meta, obs = CTDParser.parse_csv(SAMPLE_CSV_CTD)
        self.assertEqual(meta["total_levels"], 5)
        self.assertEqual(meta["max_depth_m"], 100.0)
        self.assertEqual(obs[0]["depth_m"], 1.0)
        self.assertEqual(obs[0]["temperature_c"], 28.45)
        self.assertEqual(obs[0]["quality_flag"], 1)

    def test_parse_sbe_cnv(self):
        meta, obs = CTDParser.parse_cnv(SAMPLE_SBE_CNV)
        self.assertEqual(meta["total_levels"], 3)
        self.assertAlmostEqual(obs[0]["pressure_dbar"], 1.50)
        self.assertEqual(obs[0]["temperature_c"], 28.3201)
        self.assertEqual(obs[0]["salinity_psu"], 35.1102)

    def test_parse_adcp(self):
        meta, obs = ADCPParser.parse(SAMPLE_ADCP_CSV)
        self.assertEqual(meta["total_levels"], 4)
        # Vector speed check: sqrt(0.35^2 + 0.42^2) ~ 0.547 m/s
        self.assertAlmostEqual(obs[0]["current_speed_ms"], 0.547, places=2)
        self.assertIsNotNone(obs[0]["current_direction_deg"])

    @patch("app.modules.research_files.upload_service.upload_service.upload_file")
    def test_ingest_and_query_profile(self, mock_upload):
        mock_upload.return_value = {
            "filename": "station_01.csv",
            "bucket_name": "marine-research",
            "storage_key": "oceanography/2026/11/station_01.csv",
            "category": "oceanography",
            "mime_type": "text/csv",
            "file_size_bytes": 512,
            "sha256_checksum": "sha_ctd_01",
            "uploaded_at": "2026-11-26T10:00:00Z",
        }

        profile, count = self.service.ingest_profile(
            db=self.db,
            instrument_type="CTD",
            station_name="STN-ARABIAN-01",
            latitude=14.5,
            longitude=69.0,
            profile_content=SAMPLE_CSV_CTD,
            filename="station_01.csv",
            expedition_id="EXP-2024-MONSOON",
        )
        self.assertIsNotNone(profile.id)
        self.assertEqual(count, 5)

        # Query list
        res_list = self.service.list_profiles(self.db, instrument_type="CTD")
        self.assertEqual(res_list["total"], 1)

        # Query details with observations
        details = self.service.get_profile_details(self.db, profile.id)
        self.assertEqual(len(details["observations"]), 5)
        self.assertEqual(details["observations"][0]["temperature_c"], 28.45)

    @patch("app.modules.research_files.upload_service.upload_service.upload_file")
    def test_api_ctd_and_adcp_routes(self, mock_upload):
        mock_upload.return_value = {
            "filename": "api_ctd.csv",
            "bucket_name": "marine-research",
            "storage_key": "oceanography/2026/11/api_ctd.csv",
            "category": "oceanography",
            "mime_type": "text/csv",
            "file_size_bytes": 256,
            "sha256_checksum": "sha_api_ctd",
            "uploaded_at": "2026-11-26T10:00:00Z",
        }

        # 1. Upload CTD via API
        files = {"file": ("api_ctd.csv", SAMPLE_CSV_CTD.encode("utf-8"), "text/csv")}
        data = {
            "station_name": "API-STN-02",
            "latitude": 12.0,
            "longitude": 72.0,
            "expedition_id": "EXP-API",
        }
        resp = self.client.post("/api/v1/oceanography/profiles/ctd/upload", files=files, data=data)
        self.assertEqual(resp.status_code, 201)
        profile_id = resp.json()["profile_id"]

        # 2. Detail query
        resp_det = self.client.get(f"/api/v1/oceanography/profiles/{profile_id}")
        self.assertEqual(resp_det.status_code, 200)
        self.assertEqual(resp_det.json()["station_name"], "API-STN-02")
        self.assertEqual(len(resp_det.json()["observations"]), 5)


if __name__ == "__main__":
    unittest.main()
