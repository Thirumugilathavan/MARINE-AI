"""
Unit tests for NOAA Data Provider.
"""

import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.modules.data_sources.base import UnifiedRetrievalParams
from app.modules.data_sources.noaa.service import NOAAMarineProvider
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
    InvalidBoundsError,
)


class TestNOAAProvider(unittest.TestCase):
    def setUp(self):
        self.provider = NOAAMarineProvider()

    def test_metadata(self):
        meta = self.provider.metadata()
        self.assertEqual(meta.provider_id, "noaa")
        self.assertIn("Oceanic and Atmospheric", meta.name)
        self.assertFalse(meta.authentication_required)
        self.assertEqual(meta.access_method, "erddap_griddap_rest")

    def test_list_and_get_dataset(self):
        datasets = self.provider.list_datasets()
        self.assertGreater(len(datasets), 0)
        ds_ids = [d.dataset_id for d in datasets]
        self.assertIn("ncdcOisst21Agg_LonPM180", ds_ids)

        oisst = self.provider.get_dataset("ncdcOisst21Agg_LonPM180")
        self.assertEqual(oisst.product_id, "NOAA_OISST_V2_1_FINAL")
        self.assertIn("sst", oisst.available_variables)

    def test_unknown_dataset(self):
        with self.assertRaises(DatasetNotFoundError):
            self.provider.get_dataset("non_existent_dataset")

    def test_validate_parameters_success(self):
        params = UnifiedRetrievalParams(
            provider_id="noaa",
            dataset_id="ncdcOisst21Agg_LonPM180",
            variables=["sst", "anom"],
            minimum_longitude=65.0,
            maximum_longitude=75.0,
            minimum_latitude=10.0,
            maximum_latitude=20.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-03T00:00:00Z",
        )
        validated = self.provider.validate_parameters(params)
        self.assertEqual(validated.dataset_id, "ncdcOisst21Agg_LonPM180")

    def test_validate_parameters_invalid_variable(self):
        params = UnifiedRetrievalParams(
            provider_id="noaa",
            dataset_id="ncdcOisst21Agg_LonPM180",
            variables=["invalid_var"],
            minimum_longitude=65.0,
            maximum_longitude=75.0,
            minimum_latitude=10.0,
            maximum_latitude=20.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-03T00:00:00Z",
        )
        with self.assertRaises(InvalidVariableError):
            self.provider.validate_parameters(params)

    def test_validate_parameters_inverted_bounds(self):
        params = UnifiedRetrievalParams(
            provider_id="noaa",
            dataset_id="ncdcOisst21Agg_LonPM180",
            variables=["sst"],
            minimum_longitude=85.0,
            maximum_longitude=75.0,  # inverted
            minimum_latitude=10.0,
            maximum_latitude=20.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-03T00:00:00Z",
        )
        with self.assertRaises(InvalidBoundsError):
            self.provider.validate_parameters(params)

    def test_preview(self):
        params = UnifiedRetrievalParams(
            provider_id="noaa",
            dataset_id="ncdcOisst21Agg_LonPM180",
            variables=["sst"],
            minimum_longitude=65.0,
            maximum_longitude=75.0,
            minimum_latitude=10.0,
            maximum_latitude=20.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-03T00:00:00Z",
        )
        preview = self.provider.preview(params)
        self.assertIn(preview.status, ["valid", "success"])
        self.assertGreater(preview.estimated_size_mb, 0)
        self.assertEqual(preview.bounding_box_area_deg2, 100.0)


if __name__ == "__main__":
    unittest.main()
