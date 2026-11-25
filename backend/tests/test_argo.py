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

    def test_argo_qc_and_data_mode_distinction(self):
        import numpy as np
        import xarray as xr
        import tempfile
        from pathlib import Path

        # Create synthetic Argo dataset with R, A, D modes and mixed QC flags
        n_rows = 10
        ds = xr.Dataset(
            data_vars={
                "temp": ("row", np.array([28.5, 27.2, 99.9, -10.0, 26.1, 25.0, 24.2, 23.1, 22.0, 21.0])),
                "temp_qc": ("row", np.array([1, 1, 4, 3, 2, 1, 1, 9, 1, 2])),  # 1=good, 3/4=bad, 9=missing
                "psal": ("row", np.array([35.1, 35.2, 35.0, 34.8, 35.2, 35.3, 35.4, 35.5, 35.1, 35.0])),
                "psal_qc": ("row", np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1])),
                "pres": ("row", np.array([5.0, 10.0, 20.0, 30.0, 50.0, 100.0, 200.0, 500.0, 1000.0, 1500.0])),
                "pres_qc": ("row", np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1])),
                "latitude": ("row", np.array([12.5] * n_rows)),
                "longitude": ("row", np.array([85.0] * n_rows)),
                "time": ("row", np.array(["2024-01-01T00:00:00"] * n_rows, dtype="datetime64[ns]")),
                "platform_number": ("row", np.array(["2902123"] * 5 + ["2902124"] * 5)),
                "cycle_number": ("row", np.array([1, 1, 1, 1, 1, 2, 2, 2, 2, 2])),
                "data_mode": ("row", np.array(["R", "R", "A", "A", "A", "D", "D", "D", "D", "D"])),
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_argo_qc.nc"
            ds.to_netcdf(test_file)

            params = UnifiedRetrievalParams(
                provider_id="argo",
                dataset_id="ArgoFloats",
                variables=["temp", "psal", "pres"],
                minimum_longitude=80.0,
                maximum_longitude=90.0,
                minimum_latitude=10.0,
                maximum_latitude=15.0,
                start_datetime="2024-01-01T00:00:00Z",
                end_datetime="2024-01-05T00:00:00Z",
            )

            val_res = self.provider.validate_data(test_file, expected_params=params)

            # 1. Distinguishable data modes
            meta = val_res.additional_metadata
            self.assertEqual(meta["data_modes_distribution"], {"R": 2, "A": 3, "D": 5})

            # 2. Distinct WMO platforms and profiles preserved
            self.assertEqual(meta["unique_wmo_platforms_count"], 2)
            self.assertEqual(meta["unique_vertical_profiles_count"], 2)

            # 3. QC flags explicitly counted and associated with variables
            temp_stats = val_res.variable_statistics["temp"]
            self.assertEqual(temp_stats.qc_flag_counts.get("flag_1"), 5)
            self.assertEqual(temp_stats.qc_flag_counts.get("flag_2"), 2)
            self.assertEqual(temp_stats.qc_flag_counts.get("flag_3"), 1)
            self.assertEqual(temp_stats.qc_flag_counts.get("flag_4"), 1)
            self.assertEqual(temp_stats.qc_flag_counts.get("flag_9"), 1)

            # 4. Bad measurements (QC=3,4) explicitly warned and not silently treated as good
            self.assertTrue(any("questionable/bad measurements (QC flags 3 or 4)" in w for w in val_res.warnings))


if __name__ == "__main__":
    unittest.main()
