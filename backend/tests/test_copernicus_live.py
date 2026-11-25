"""
Live integration tests for Copernicus Marine Service.

Performs live operations against the Copernicus Marine Data Store:
- Live catalogue metadata verification for all candidate dataset IDs.
- Live retrieval attempt for a small Indian Ocean spatial cell (60°E - 60.5°E, 10°N - 10.5°N)
  when credentials are provided, or verification of the authentication gate.
"""

import os
import unittest
from pathlib import Path

from app.core.config import settings
from app.modules.data_sources.copernicus.constants import (
    DEFAULT_INDIAN_OCEAN_BOUNDS,
    DATASET_NRT_DAILY_THETAO,
    DATASET_HISTORICAL_DAILY,
    DATASET_NRT_SIX_HOURLY_CURRENTS,
)
from app.modules.data_sources.copernicus.service import (
    get_verified_datasets,
    retrieve_copernicus_subset,
)
from app.modules.validation.marine_validator import BoundingBox


class TestCopernicusLiveIntegration(unittest.TestCase):
    """
    Live tests connecting to Copernicus Marine endpoints.
    These tests interact with external network services.
    """

    def test_live_verified_dataset_constants(self):
        """Verifies that all defined dataset constants match the platform registry."""
        data = get_verified_datasets()
        self.assertEqual(data["provider"], "Copernicus Marine Service")
        self.assertEqual(data["target_region"], "Indian Ocean")
        self.assertEqual(data["default_bounding_box"], DEFAULT_INDIAN_OCEAN_BOUNDS)

        # Check cadences
        cadences = data["cadences"]
        self.assertIn("nrt_six_hourly", cadences)
        self.assertIn("nrt_daily", cadences)
        self.assertIn("historical_daily", cadences)

        # Verify dataset IDs in registry
        nrt_daily_vars = cadences["nrt_daily"]["variable_datasets"]
        self.assertEqual(nrt_daily_vars["thetao"], DATASET_NRT_DAILY_THETAO)
        self.assertEqual(cadences["historical_daily"]["variable_datasets"]["thetao"], DATASET_HISTORICAL_DAILY)

    def test_live_bounded_retrieval_or_auth_check(self):
        """
        Attempts a bounded retrieval for a tiny Indian Ocean cell:
        Longitude: 60.0 to 60.5, Latitude: 10.0 to 10.5 (Arabian Sea).
        If credentials exist in settings, performs live download.
        If credentials do not exist, confirms graceful authentication_required handling.
        """
        small_indian_ocean_bbox = BoundingBox(
            minimum_longitude=60.0,
            maximum_longitude=60.5,
            minimum_latitude=10.0,
            maximum_latitude=10.5,
        )

        has_credentials = bool(settings.copernicus_marine_username and settings.copernicus_marine_password)

        if has_credentials:
            print("\n[LIVE TEST] Executing real Copernicus subset with provided credentials...")
            result = retrieve_copernicus_subset(
                cadence="nrt_daily",
                variables=["thetao"],
                bounding_box=small_indian_ocean_bbox,
                minimum_depth=0.0,
                maximum_depth=5.0,
                dry_run=False,
            )
            self.assertIn(result["status"], ["success", "partial_failure"])
            print(f"[LIVE TEST RESULT] Status: {result['status']}, Files: {len(result['downloaded_files'])}")
        else:
            print("\n[LIVE AUTH CHECK] Testing Copernicus authentication handling without credentials...")
            result = retrieve_copernicus_subset(
                cadence="nrt_daily",
                variables=["thetao"],
                bounding_box=small_indian_ocean_bbox,
                dry_run=False,
            )
            self.assertEqual(result["status"], "authentication_required")
            self.assertIn("https://data.marine.copernicus.eu/register", result["message"])
            print("[LIVE AUTH CHECK RESULT] Authentication requirement gracefully detected and handled.")


if __name__ == "__main__":
    unittest.main()
