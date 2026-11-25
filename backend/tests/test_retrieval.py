"""
Unit tests for Copernicus retrieval service, boundary validation, and dry-run preview.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.modules.data_sources.copernicus.retrieval import (
    CopernicusRetrievalService,
    RetrievalParameters,
    sanitize_filename,
    MAX_ALLOWED_AREA_DEG2,
)
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
    InvalidBoundsError,
    RetrievalError,
)


class TestRetrievalService(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = CopernicusRetrievalService(staging_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _get_valid_params(self) -> RetrievalParameters:
        return RetrievalParameters(
            dataset_id="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
            variables=["thetao"],
            minimum_longitude=85.0,
            maximum_longitude=85.2,
            minimum_latitude=12.0,
            maximum_latitude=12.2,
            start_datetime="2026-11-20",
            end_datetime="2026-11-20",
            minimum_depth=0.49,
            maximum_depth=0.5,
        )

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("valid_name.nc"), "valid_name.nc")
        self.assertEqual(sanitize_filename("name_without_ext"), "name_without_ext.nc")
        # Path traversal prevention
        self.assertEqual(sanitize_filename("../../etc/passwd"), "passwd.nc")
        self.assertEqual(sanitize_filename("C:\\Windows\\System32\\bad.nc"), "bad.nc")
        # Dangerous characters and separators
        self.assertEqual(sanitize_filename("test;rm -rf /;data.nc"), "_data.nc")
        self.assertEqual(sanitize_filename("test;command|injection.nc"), "test_command_injection.nc")

    def test_valid_parameters(self):
        params = self._get_valid_params()
        dataset = self.service.validate_parameters(params)
        self.assertEqual(dataset.dataset_id, params.dataset_id)

    def test_invalid_coordinates_range(self):
        params = self._get_valid_params()
        params.minimum_longitude = -190.0
        with self.assertRaises(InvalidBoundsError):
            self.service.validate_parameters(params)

        params = self._get_valid_params()
        params.maximum_latitude = 95.0
        with self.assertRaises(InvalidBoundsError):
            self.service.validate_parameters(params)

    def test_inverted_coordinates(self):
        params = self._get_valid_params()
        params.minimum_longitude = 90.0
        params.maximum_longitude = 80.0
        with self.assertRaises(InvalidBoundsError):
            self.service.validate_parameters(params)

        params = self._get_valid_params()
        params.minimum_latitude = 20.0
        params.maximum_latitude = 10.0
        with self.assertRaises(InvalidBoundsError):
            self.service.validate_parameters(params)

    def test_area_limit_exceeded(self):
        params = self._get_valid_params()
        params.minimum_longitude = -50.0
        params.maximum_longitude = 50.0  # 100 deg
        params.minimum_latitude = -30.0
        params.maximum_latitude = 30.0   # 60 deg -> area = 6000 deg² > 2500
        with self.assertRaises(InvalidBoundsError):
            self.service.validate_parameters(params)

    def test_invalid_time_range(self):
        params = self._get_valid_params()
        params.start_datetime = "2026-11-25"
        params.end_datetime = "2026-11-20"  # start > end
        with self.assertRaises(InvalidBoundsError):
            self.service.validate_parameters(params)

        params = self._get_valid_params()
        params.start_datetime = "invalid-date"
        with self.assertRaises(InvalidBoundsError):
            self.service.validate_parameters(params)

    def test_invalid_depth_range(self):
        params = self._get_valid_params()
        params.minimum_depth = 100.0
        params.maximum_depth = 10.0  # min > max
        with self.assertRaises(InvalidBoundsError):
            self.service.validate_parameters(params)

    def test_unsupported_variable(self):
        params = self._get_valid_params()
        params.variables = ["non_existent_var"]
        with self.assertRaises(InvalidVariableError):
            self.service.validate_parameters(params)

    @patch("app.modules.data_sources.copernicus.retrieval.copernicusmarine.subset")
    def test_preview_dry_run_success(self, mock_subset):
        mock_response = MagicMock()
        mock_response.file_size = 0.013
        mock_response.data_transfer_size = 2.09
        mock_response.message = "Dry-run succeeded"
        mock_ext = MagicMock()
        mock_ext.coordinate_id = "longitude"
        mock_ext.minimum = 85.0
        mock_ext.maximum = 85.17
        mock_ext.unit = "degrees_east"
        mock_response.coordinates_extent = [mock_ext]
        mock_subset.return_value = mock_response

        params = self._get_valid_params()
        preview = self.service.preview(params, request_id="req-123")
        self.assertEqual(preview.request_id, "req-123")
        self.assertEqual(preview.estimated_file_size_mb, 0.013)
        self.assertIn("longitude", preview.selected_extent)

    @patch("app.modules.data_sources.copernicus.retrieval.copernicusmarine.subset")
    def test_execute_retrieval_success(self, mock_subset):
        job_id = "job-456"
        target_dir = Path(self.temp_dir.name) / job_id
        target_dir.mkdir(parents=True, exist_ok=True)
        fake_nc = target_dir / "test_output.nc"
        fake_nc.write_bytes(b"CDF\x02Fake NetCDF Content")

        mock_res = MagicMock()
        mock_res.file_path = str(fake_nc)
        mock_subset.return_value = mock_res

        params = self._get_valid_params()
        out_path = self.service.execute_retrieval(params, job_id=job_id)
        self.assertTrue(out_path.exists())
        self.assertEqual(out_path, fake_nc)

    @patch("app.modules.data_sources.copernicus.retrieval.copernicusmarine.subset")
    def test_execute_retrieval_failure(self, mock_subset):
        mock_subset.side_effect = RuntimeError("Connection timed out")
        params = self._get_valid_params()
        with self.assertRaises(RetrievalError):
            self.service.execute_retrieval(params, job_id="job-fail")


if __name__ == "__main__":
    unittest.main()
