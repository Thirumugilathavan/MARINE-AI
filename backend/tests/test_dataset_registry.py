"""
Unit tests for Copernicus Dataset Registry.
"""

import unittest
from app.modules.data_sources.copernicus.dataset_registry import (
    registry,
    DatasetRegistry,
    RegisteredDataset,
    VERIFIED_TEMPERATURE_DATASET,
)
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
)


class TestDatasetRegistry(unittest.TestCase):

    def setUp(self):
        self.reg = DatasetRegistry()

    def test_registered_dataset_lookup(self):
        ds = self.reg.get("cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m")
        self.assertIsNotNone(ds)
        self.assertEqual(ds.dataset_id, "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m")
        self.assertEqual(ds.product_id, "GLOBAL_ANALYSISFORECAST_PHY_001_024")
        self.assertIn("thetao", ds.available_variables)
        self.assertEqual(ds.verification_status, "verified")

    def test_unknown_dataset_rejection(self):
        self.assertIsNone(self.reg.get("non_existent_dataset"))
        with self.assertRaises(DatasetNotFoundError):
            self.reg.get_or_raise("non_existent_dataset")

    def test_variable_validation_success(self):
        # Should not raise
        self.reg.validate_variables("cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m", ["thetao"])

    def test_variable_validation_failure(self):
        with self.assertRaises(InvalidVariableError):
            self.reg.validate_variables("cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m", ["so"])

        with self.assertRaises(InvalidVariableError):
            self.reg.validate_variables("cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m", [])

    def test_metadata_serialization(self):
        ds = self.reg.get("cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m")
        data = ds.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["dataset_id"], "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m")
        self.assertIn("spatial_coverage", data)
        self.assertEqual(data["spatial_coverage"]["minimum_longitude"], -180.0)

    def test_safe_extension_mechanism(self):
        new_ds = RegisteredDataset(
            provider="Copernicus Marine Service",
            product_id="TEST_PROD",
            dataset_id="test_dataset_future",
            dataset_version="1.0",
            dataset_part="default",
            product_title="Test Future Dataset",
            dataset_description="Description of future dataset",
            available_variables=["uo", "vo"],
            variable_metadata={},
            temporal_resolution="P1D",
            spatial_resolution="0.083 deg",
            data_type="model_analysis_forecast",
            spatial_coverage={"minimum_longitude": -180.0, "maximum_longitude": 180.0, "minimum_latitude": -90.0, "maximum_latitude": 90.0},
            depth_levels_count=10,
            depth_min=0.0,
            depth_max=100.0,
            source_documentation=None,
            licence_information=None,
            verification_status="verified",
            last_metadata_verification_time="2026-11-25T00:00:00Z",
        )
        self.reg.register(new_ds)
        retrieved = self.reg.get("test_dataset_future")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.product_title, "Test Future Dataset")


if __name__ == "__main__":
    unittest.main()
