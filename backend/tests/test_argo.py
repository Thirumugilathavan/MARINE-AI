"""
Unit tests for Argo Ocean Profiling Float Data Provider.
"""

import unittest
from app.modules.data_sources.base import UnifiedRetrievalParams
from app.modules.data_sources.argo.service import ArgoMarineProvider
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
    InvalidBoundsError,
)


class TestArgoProvider(unittest.TestCase):
    def setUp(self):
        self.provider = ArgoMarineProvider()

    def test_metadata(self):
        meta = self.provider.metadata()
        self.assertEqual(meta.provider_id, "argo")
        self.assertIn("Argo", meta.name)
        self.assertFalse(meta.authentication_required)
        self.assertEqual(meta.access_method, "erddap_tabledap")

    def test_list_and_get_dataset(self):
        datasets = self.provider.list_datasets()
        self.assertGreater(len(datasets), 0)
        ds_ids = [d.dataset_id for d in datasets]
        self.assertIn("ArgoFloats", ds_ids)

        argo_meta = self.provider.get_dataset("ArgoFloats")
        self.assertEqual(argo_meta.product_id, "CORIOLIS_ARGO_GLOBAL_FLOATS")
        self.assertIn("temp", argo_meta.available_variables)
        self.assertIn("psal", argo_meta.available_variables)
        self.assertIn("pres", argo_meta.available_variables)

    def test_unknown_dataset(self):
        with self.assertRaises(DatasetNotFoundError):
            self.provider.get_dataset("non_existent_argo_dataset")

    def test_validate_parameters_success(self):
        params = UnifiedRetrievalParams(
            provider_id="argo",
            dataset_id="ArgoFloats",
            variables=["temp", "psal"],
            minimum_longitude=80.0,
            maximum_longitude=90.0,
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-05T00:00:00Z",
            minimum_depth=0.0,
            maximum_depth=2000.0,
        )
        validated = self.provider.validate_parameters(params)
        self.assertEqual(validated.dataset_id, "ArgoFloats")

    def test_validate_parameters_invalid_variable(self):
        params = UnifiedRetrievalParams(
            provider_id="argo",
            dataset_id="ArgoFloats",
            variables=["invalid_argo_var"],
            minimum_longitude=80.0,
            maximum_longitude=90.0,
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-05T00:00:00Z",
        )
        with self.assertRaises(InvalidVariableError):
            self.provider.validate_parameters(params)

    def test_validate_parameters_invalid_depth(self):
        params = UnifiedRetrievalParams(
            provider_id="argo",
            dataset_id="ArgoFloats",
            variables=["temp"],
            minimum_longitude=80.0,
            maximum_longitude=90.0,
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-05T00:00:00Z",
            minimum_depth=500.0,
            maximum_depth=200.0,  # inverted
        )
        with self.assertRaises(InvalidBoundsError):
            self.provider.validate_parameters(params)

    def test_preview(self):
        params = UnifiedRetrievalParams(
            provider_id="argo",
            dataset_id="ArgoFloats",
            variables=["temp", "psal"],
            minimum_longitude=80.0,
            maximum_longitude=90.0,
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-05T00:00:00Z",
        )
        preview = self.provider.preview(params)
        self.assertEqual(preview.status, "success")
        self.assertGreater(preview.estimated_size_mb, 0)
        self.assertEqual(preview.bounding_box_area_deg2, 50.0)

    def test_build_tabledap_url(self):
        params = UnifiedRetrievalParams(
            provider_id="argo",
            dataset_id="ArgoFloats",
            variables=["temp"],
            minimum_longitude=80.0,
            maximum_longitude=90.0,
            minimum_latitude=10.0,
            maximum_latitude=15.0,
            start_datetime="2024-01-01T00:00:00Z",
            end_datetime="2024-01-05T00:00:00Z",
        )
        url = self.provider._build_tabledap_url(params)
        self.assertIn("tabledap/ArgoFloats.nc", url)
        self.assertIn("latitude>=", url)
        self.assertIn("longitude>=", url)
        self.assertIn("time>=", url)
        self.assertIn("temp", url)
        self.assertIn("temp_qc", url)


if __name__ == "__main__":
    unittest.main()
