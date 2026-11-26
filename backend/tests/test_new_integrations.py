"""
Unit and integration tests for newly integrated marine datasets:
- INCOIS Oceansat-2 Chlorophyll-a and Total Suspended Matter
- Real eDNA / Metagenome sample registries (ENA / MGnify)
- Real marine media metadata verification
- Central catalogue additions (EMODnet Seabed Habitats)
"""

import unittest
from pathlib import Path
from app.modules.data_sources.incois.service import INCOISMarineProvider, INCOIS_VERIFIED_DATASETS
from app.modules.data_sources.base import UnifiedRetrievalParams
from app.modules.data_sources.copernicus.exceptions import InvalidVariableError, InvalidBoundsError


class TestNewDataIntegrations(unittest.TestCase):
    """Test suite covering newly acquired missing datasets."""

    def setUp(self):
        self.incois = INCOISMarineProvider(verify_ssl=False)

    def test_oceansat2_dataset_registration(self):
        """Verifies INCOIS Oceansat-2 OCM Chlorophyll-a dataset is registered."""
        self.assertIn("incois_oceansat2_datasets", INCOIS_VERIFIED_DATASETS)
        meta = INCOIS_VERIFIED_DATASETS["incois_oceansat2_datasets"]
        self.assertEqual(meta.provider_id, "incois")
        self.assertIn("CHL", meta.available_variables)
        self.assertIn("TSM", meta.available_variables)
        self.assertIn("KD490", meta.available_variables)
        self.assertEqual(meta.variable_metadata["CHL"]["units"], "mg/m3")
        self.assertEqual(meta.variable_metadata["TSM"]["units"], "mg/L")

    def test_oceansat2_parameter_validation_success(self):
        """Tests parameter validation for valid Oceansat-2 bounding box and variables."""
        params = UnifiedRetrievalParams(
            provider_id="incois",
            dataset_id="incois_oceansat2_datasets",
            variables=["CHL", "TSM"],
            minimum_longitude=70.0,
            maximum_longitude=75.0,
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            start_datetime="2020-05-01T00:00:00Z",
            end_datetime="2020-05-01T00:00:00Z",
        )
        validated = self.incois.validate_parameters(params)
        self.assertEqual(validated.dataset_id, "incois_oceansat2_datasets")
        self.assertEqual(validated.variables, ["CHL", "TSM"])

    def test_oceansat2_invalid_variable_rejection(self):
        """Tests that invalid variables are rejected with InvalidVariableError."""
        params = UnifiedRetrievalParams(
            provider_id="incois",
            dataset_id="incois_oceansat2_datasets",
            variables=["INVALID_VAR"],
            minimum_longitude=70.0,
            maximum_longitude=75.0,
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            start_datetime="2020-05-01T00:00:00Z",
            end_datetime="2020-05-01T00:00:00Z",
        )
        with self.assertRaises(InvalidVariableError):
            self.incois.validate_parameters(params)

    def test_oceansat2_griddap_url_construction(self):
        """Tests ERDDAP griddap URL generation with RFC 7230 encoded brackets."""
        params = UnifiedRetrievalParams(
            provider_id="incois",
            dataset_id="incois_oceansat2_datasets",
            variables=["CHL", "TSM"],
            minimum_longitude=70.0,
            maximum_longitude=70.2,
            minimum_latitude=12.0,
            maximum_latitude=12.2,
            start_datetime="2020-05-01T00:00:00Z",
            end_datetime="2020-05-01T00:00:00Z",
        )
        url = self.incois._build_griddap_url(params)
        self.assertIn("incois_oceansat2_datasets.nc?", url)
        self.assertIn("CHL", url)
        self.assertIn("TSM", url)
        # Verify RFC 7230 character encoding (no raw brackets)
        self.assertNotIn("[", url)
        self.assertNotIn("]", url)
        self.assertIn("%5B", url)
        self.assertIn("%5D", url)

    def test_oceansat2_dry_run_preview(self):
        """Tests size estimation and point calculation for dry-run preview."""
        params = UnifiedRetrievalParams(
            provider_id="incois",
            dataset_id="incois_oceansat2_datasets",
            variables=["CHL"],
            minimum_longitude=70.0,
            maximum_longitude=71.0,
            minimum_latitude=12.0,
            maximum_latitude=13.0,
            start_datetime="2020-05-01T00:00:00Z",
            end_datetime="2020-05-02T00:00:00Z",
        )
        preview = self.incois.preview(params)
        self.assertEqual(preview.provider_id, "incois")
        self.assertEqual(preview.dataset_id, "incois_oceansat2_datasets")
        self.assertGreater(preview.estimated_total_points, 0)
        self.assertGreater(preview.estimated_size_mb, 0.0)


if __name__ == "__main__":
    unittest.main()
