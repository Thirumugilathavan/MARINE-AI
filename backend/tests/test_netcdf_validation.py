"""
Tests for NetCDF validation module and the real Copernicus Bay of Bengal test fixture.
"""

from pathlib import Path
import tempfile
from typing import Optional, Dict, Any
import unittest
import numpy as np
import xarray as xr

from app.modules.data_sources.copernicus.validation import (
    NetCDFValidator,
    ValidationReport,
)

FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "dataset-staging" / "copernicus-test" / "bay_of_bengal_thetao_test.nc"


class TestNetCDFValidation(unittest.TestCase):

    def setUp(self):
        self.validator = NetCDFValidator()
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_real_bay_of_bengal_fixture(self):
        """
        Integration test verifying the real Copernicus Bay of Bengal retrieval fixture:
        D:\\SSTRIX_MARINE_PLATFORM\\dataset-staging\\copernicus-test\\bay_of_bengal_thetao_test.nc
        """
        if not FIXTURE_PATH.exists():
            self.skipTest(f"Fixture {FIXTURE_PATH} not found on this machine (skipping local integration test).")

        report = self.validator.validate_file(
            file_path=FIXTURE_PATH,
            expected_dataset_id="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
            expected_variables=["thetao"],
            expected_bounds={
                "minimum_longitude": 85.0,
                "maximum_longitude": 85.2,
                "minimum_latitude": 12.0,
                "maximum_latitude": 12.2,
            },
        )

        self.assertEqual(report.status, "passed")
        self.assertTrue(report.is_valid)
        self.assertEqual(len(report.errors), 0)

        # Dimension checks
        self.assertEqual(report.dimensions.get("time"), 1)
        self.assertEqual(report.dimensions.get("depth"), 1)
        self.assertEqual(report.dimensions.get("latitude"), 3)
        self.assertEqual(report.dimensions.get("longitude"), 3)

        # Variable statistics
        self.assertIn("thetao", report.variable_stats)
        stats = report.variable_stats["thetao"]
        self.assertEqual(stats.total_points, 9)
        self.assertEqual(stats.valid_points, 9)
        self.assertEqual(stats.missing_points, 0)
        self.assertEqual(stats.units, "degrees_C")
        self.assertEqual(stats.standard_name, "sea_water_potential_temperature")

        # Range checks: approximately 29.229 to 29.286 °C
        self.assertAlmostEqual(stats.min_value, 29.2290, places=3)
        self.assertAlmostEqual(stats.max_value, 29.2862, places=3)
        self.assertAlmostEqual(stats.mean_value, 29.2641, places=3)

    def _create_synthetic_nc(
        self,
        filename: str,
        var_name: str = "thetao",
        data: Optional[np.ndarray] = None,
        units: str = "degrees_C",
        attrs: Optional[dict] = None,
    ) -> Path:
        """Helper to create small synthetic NetCDF datasets for edge cases."""
        if data is None:
            data = np.array([[[[25.0, 26.0], [27.0, 28.0]]]], dtype=np.float32)

        time_coord = np.array(["2026-11-20T00:00:00"], dtype="datetime64[ns]")
        depth_coord = np.array([0.494], dtype=np.float32)
        lat_coord = np.array([12.0, 12.08], dtype=np.float32)
        lon_coord = np.array([85.0, 85.08], dtype=np.float32)

        var_attrs = {"units": units, "standard_name": "sea_water_potential_temperature"}
        if attrs:
            var_attrs.update(attrs)

        ds = xr.Dataset(
            data_vars={
                var_name: (["time", "depth", "latitude", "longitude"], data, var_attrs)
            },
            coords={
                "time": time_coord,
                "depth": depth_coord,
                "latitude": lat_coord,
                "longitude": lon_coord,
            },
            attrs={"Conventions": "CF-1.8", "title": "Synthetic Test Dataset"},
        )

        out_path = Path(self.temp_dir.name) / filename
        ds.to_netcdf(out_path)
        ds.close()
        return out_path

    def test_missing_file(self):
        report = self.validator.validate_file("non_existent_file.nc")
        self.assertEqual(report.status, "failed")
        self.assertFalse(report.is_valid)
        self.assertIn("File not found", report.errors[0])

    def test_empty_corrupt_file(self):
        empty_file = Path(self.temp_dir.name) / "empty.nc"
        empty_file.write_bytes(b"")
        report = self.validator.validate_file(empty_file)
        self.assertEqual(report.status, "failed")
        self.assertFalse(report.is_valid)

    def test_missing_expected_variable(self):
        nc_path = self._create_synthetic_nc("missing_var.nc", var_name="so")
        report = self.validator.validate_file(nc_path, expected_variables=["thetao"])
        self.assertEqual(report.status, "failed")
        self.assertFalse(report.is_valid)
        self.assertTrue(any("thetao" in err for err in report.errors))

    def test_nan_missing_values(self):
        # 2 valid values, 2 NaNs
        data_with_nans = np.array([[[[25.0, np.nan], [np.nan, 28.0]]]], dtype=np.float32)
        nc_path = self._create_synthetic_nc("nans.nc", data=data_with_nans)

        report = self.validator.validate_file(nc_path, expected_variables=["thetao"])
        self.assertEqual(report.status, "passed")
        self.assertTrue(report.is_valid)
        stats = report.variable_stats["thetao"]
        self.assertEqual(stats.total_points, 4)
        self.assertEqual(stats.valid_points, 2)
        self.assertEqual(stats.missing_points, 2)
        self.assertEqual(stats.min_value, 25.0)
        self.assertEqual(stats.max_value, 28.0)

    def test_out_of_range_values(self):
        # Temperature out of physical range (> 40 °C)
        data_oob = np.array([[[[25.0, 99.0], [27.0, 28.0]]]], dtype=np.float32)
        nc_path = self._create_synthetic_nc(
            "oob.nc",
            data=data_oob,
            attrs={"valid_min": -10.0, "valid_max": 40.0},
        )

        report = self.validator.validate_file(
            nc_path,
            expected_dataset_id="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
            expected_variables=["thetao"],
        )
        self.assertEqual(report.status, "warnings")
        stats = report.variable_stats["thetao"]
        self.assertEqual(stats.out_of_range_points, 1)
        self.assertTrue(len(stats.warnings) > 0)

    def test_unit_mismatch(self):
        nc_path = self._create_synthetic_nc("wrong_units.nc", units="Kelvin")
        report = self.validator.validate_file(
            nc_path,
            expected_dataset_id="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
            expected_variables=["thetao"],
        )
        self.assertEqual(report.status, "warnings")
        self.assertTrue(any("units" in w for w in report.warnings))


if __name__ == "__main__":
    unittest.main()
