"""
Unit tests for INCOIS Data Provider.
"""

import unittest
from app.modules.data_sources.base import UnifiedRetrievalParams
from app.modules.data_sources.incois.service import INCOISMarineProvider
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
    InvalidBoundsError,
)


class TestINCOISProvider(unittest.TestCase):
    def setUp(self):
        self.provider = INCOISMarineProvider()

    def test_metadata(self):
        meta = self.provider.metadata()
        self.assertEqual(meta.provider_id, "incois")
        self.assertIn("Ocean Information Services", meta.name)
        self.assertFalse(meta.authentication_required)
        self.assertEqual(meta.access_method, "erddap_griddap")

    def test_list_and_get_dataset(self):
        datasets = self.provider.list_datasets()
        self.assertGreater(len(datasets), 0)
        ds_ids = [d.dataset_id for d in datasets]
        self.assertIn("ascat_daily_datasets", ds_ids)

        ascat = self.provider.get_dataset("ascat_daily_datasets")
        self.assertEqual(ascat.product_id, "INCOIS_ASCAT_DAILY_WIND")
        self.assertIn("wind_speed", ascat.available_variables)
        self.assertIn("wind_stress", ascat.available_variables)

    def test_unknown_dataset(self):
        with self.assertRaises(DatasetNotFoundError):
            self.provider.get_dataset("non_existent_incois_dataset")

    def test_validate_parameters_success(self):
        params = UnifiedRetrievalParams(
            provider_id="incois",
            dataset_id="ascat_daily_datasets",
            variables=["wind_speed"],
            minimum_longitude=65.0,
            maximum_longitude=75.0,
            minimum_latitude=10.0,
            maximum_latitude=20.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-03T00:00:00Z",
        )
        validated = self.provider.validate_parameters(params)
        self.assertEqual(validated.dataset_id, "ascat_daily_datasets")

    def test_validate_parameters_invalid_variable(self):
        params = UnifiedRetrievalParams(
            provider_id="incois",
            dataset_id="ascat_daily_datasets",
            variables=["unsupported_wind_var"],
            minimum_longitude=65.0,
            maximum_longitude=75.0,
            minimum_latitude=10.0,
            maximum_latitude=20.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-03T00:00:00Z",
        )
        with self.assertRaises(InvalidVariableError):
            self.provider.validate_parameters(params)

    def test_griddap_url_encoding(self):
        params = UnifiedRetrievalParams(
            provider_id="incois",
            dataset_id="ascat_daily_datasets",
            variables=["wind_speed"],
            minimum_longitude=65.0,
            maximum_longitude=75.0,
            minimum_latitude=10.0,
            maximum_latitude=20.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-03T00:00:00Z",
        )
        url = self.provider._build_griddap_url(params)
        # Verify Tomcat bracket encoding
        self.assertNotIn("[", url)
        self.assertNotIn("]", url)
        self.assertIn("%5B", url)
        self.assertIn("%5D", url)
        self.assertIn("ascat_daily_datasets.nc", url)

    def test_preview(self):
        params = UnifiedRetrievalParams(
            provider_id="incois",
            dataset_id="ascat_daily_datasets",
            variables=["wind_speed"],
            minimum_longitude=65.0,
            maximum_longitude=75.0,
            minimum_latitude=10.0,
            maximum_latitude=20.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-03T00:00:00Z",
        )
        preview = self.provider.preview(params)
        self.assertEqual(preview.status, "success")
        self.assertGreater(preview.estimated_size_mb, 0)
        self.assertEqual(preview.bounding_box_area_deg2, 100.0)


if __name__ == "__main__":
    unittest.main()
