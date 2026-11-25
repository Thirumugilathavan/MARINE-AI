"""
Copernicus Marine retrieval service using copernicusmarine.subset().

Implements parameter validation, boundary checking, request preview/dry-run,
path traversal prevention, and bounded dataset retrieval.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from typing import Dict, List, Optional, Any

import copernicusmarine

from app.core.config import settings
from app.modules.data_sources.copernicus.dataset_registry import registry, RegisteredDataset
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
    InvalidBoundsError,
    RetrievalError,
)

logger = logging.getLogger(__name__)

# Safety limits to prevent accidental global / unconstrained downloads
MAX_ALLOWED_AREA_DEG2 = 2500.0  # e.g., 50x50 degrees
MAX_ALLOWED_DAYS = 365


@dataclass
class RetrievalParameters:
    dataset_id: str
    variables: List[str]
    minimum_longitude: float
    maximum_longitude: float
    minimum_latitude: float
    maximum_latitude: float
    start_datetime: str
    end_datetime: str
    minimum_depth: Optional[float] = None
    maximum_depth: Optional[float] = None
    dataset_version: Optional[str] = None
    dataset_part: Optional[str] = None
    output_filename: Optional[str] = None


@dataclass
class PreviewResponse:
    request_id: str
    dataset_id: str
    product_id: str
    product_title: str
    requested_variables: List[str]
    requested_extent: Dict[str, float]
    selected_extent: Dict[str, Any]
    time_range: Dict[str, str]
    depth_range: Dict[str, Optional[float]]
    estimated_file_size_mb: float
    estimated_data_transfer_mb: float
    dry_run_status: str
    dry_run_message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def sanitize_filename(filename: str) -> str:
    """
    Prevents directory traversal and strips illegal characters.
    """
    clean = Path(filename).name
    clean = re.sub(r"[^a-zA-Z0-9_\.-]", "_", clean)
    if not clean.endswith(".nc"):
        clean += ".nc"
    return clean


class CopernicusRetrievalService:
    """
    Handles validated subset requests to Copernicus Marine.
    """

    def __init__(self, staging_dir: Optional[Path] = None):
        if staging_dir:
            self.staging_dir = Path(staging_dir)
        else:
            self.staging_dir = Path.cwd() / "dataset-staging" / "copernicus"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def validate_parameters(self, params: RetrievalParameters) -> RegisteredDataset:
        """
        Validates all retrieval parameters against registered dataset metadata and safety limits.
        """
        # 1. Dataset existence
        dataset = registry.get_or_raise(params.dataset_id)

        # 2. Variables validation
        registry.validate_variables(params.dataset_id, params.variables)

        # 3. Coordinate validation
        if not (-180.0 <= params.minimum_longitude <= 180.0):
            raise InvalidBoundsError(f"minimum_longitude {params.minimum_longitude} out of range [-180, 180]")
        if not (-180.0 <= params.maximum_longitude <= 180.0):
            raise InvalidBoundsError(f"maximum_longitude {params.maximum_longitude} out of range [-180, 180]")
        if not (-90.0 <= params.minimum_latitude <= 90.0):
            raise InvalidBoundsError(f"minimum_latitude {params.minimum_latitude} out of range [-90, 90]")
        if not (-90.0 <= params.maximum_latitude <= 90.0):
            raise InvalidBoundsError(f"maximum_latitude {params.maximum_latitude} out of range [-90, 90]")

        if params.minimum_longitude > params.maximum_longitude:
            raise InvalidBoundsError(
                f"minimum_longitude ({params.minimum_longitude}) must be <= maximum_longitude ({params.maximum_longitude})"
            )
        if params.minimum_latitude > params.maximum_latitude:
            raise InvalidBoundsError(
                f"minimum_latitude ({params.minimum_latitude}) must be <= maximum_latitude ({params.maximum_latitude})"
            )

        # Area limit check
        lon_span = params.maximum_longitude - params.minimum_longitude
        lat_span = params.maximum_latitude - params.minimum_latitude
        area_deg2 = lon_span * lat_span
        if area_deg2 > MAX_ALLOWED_AREA_DEG2:
            raise InvalidBoundsError(
                f"Requested bounding box area ({area_deg2:.1f} deg²) exceeds safety limit ({MAX_ALLOWED_AREA_DEG2} deg²). "
                "Please request a smaller geographic subset."
            )

        # 4. Temporal range validation
        try:
            start_dt = datetime.fromisoformat(params.start_datetime.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(params.end_datetime.replace("Z", "+00:00"))
        except Exception as exc:
            raise InvalidBoundsError(f"Invalid ISO 8601 datetime format for start/end: {exc}")

        if start_dt > end_dt:
            raise InvalidBoundsError(
                f"start_datetime ({params.start_datetime}) must be <= end_datetime ({params.end_datetime})"
            )

        days_span = (end_dt - start_dt).days
        if days_span > MAX_ALLOWED_DAYS:
            raise InvalidBoundsError(
                f"Requested time interval ({days_span} days) exceeds maximum allowed limit ({MAX_ALLOWED_DAYS} days)."
            )

        # 5. Depth range validation
        if params.minimum_depth is not None and params.maximum_depth is not None:
            if params.minimum_depth > params.maximum_depth:
                raise InvalidBoundsError(
                    f"minimum_depth ({params.minimum_depth}) must be <= maximum_depth ({params.maximum_depth})"
                )

        return dataset

    def preview(self, params: RetrievalParameters, request_id: str) -> PreviewResponse:
        """
        Executes a dry-run subset query against Copernicus Marine to estimate size and coordinates.
        Does not download any data file.
        """
        dataset = self.validate_parameters(params)

        try:
            dry_run_res = copernicusmarine.subset(
                dataset_id=params.dataset_id,
                dataset_version=params.dataset_version or dataset.dataset_version,
                dataset_part=params.dataset_part or dataset.dataset_part,
                variables=params.variables,
                minimum_longitude=params.minimum_longitude,
                maximum_longitude=params.maximum_longitude,
                minimum_latitude=params.minimum_latitude,
                maximum_latitude=params.maximum_latitude,
                start_datetime=params.start_datetime,
                end_datetime=params.end_datetime,
                minimum_depth=params.minimum_depth,
                maximum_depth=params.maximum_depth,
                dry_run=True,
                disable_progress_bar=True,
            )

            # Extract extents from dry-run response
            selected_extent: Dict[str, Any] = {}
            if hasattr(dry_run_res, "coordinates_extent") and dry_run_res.coordinates_extent:
                for ext in dry_run_res.coordinates_extent:
                    coord_id = getattr(ext, "coordinate_id", "unknown")
                    selected_extent[coord_id] = {
                        "min": getattr(ext, "minimum", None),
                        "max": getattr(ext, "maximum", None),
                        "unit": getattr(ext, "unit", None),
                    }

            file_size_mb = float(getattr(dry_run_res, "file_size", 0.0) or 0.0)
            data_transfer_mb = float(getattr(dry_run_res, "data_transfer_size", 0.0) or 0.0)

            return PreviewResponse(
                request_id=request_id,
                dataset_id=params.dataset_id,
                product_id=dataset.product_id,
                product_title=dataset.product_title,
                requested_variables=params.variables,
                requested_extent={
                    "minimum_longitude": params.minimum_longitude,
                    "maximum_longitude": params.maximum_longitude,
                    "minimum_latitude": params.minimum_latitude,
                    "maximum_latitude": params.maximum_latitude,
                },
                selected_extent=selected_extent,
                time_range={"start": params.start_datetime, "end": params.end_datetime},
                depth_range={"minimum_depth": params.minimum_depth, "maximum_depth": params.maximum_depth},
                estimated_file_size_mb=round(file_size_mb, 4),
                estimated_data_transfer_mb=round(data_transfer_mb, 4),
                dry_run_status="success",
                dry_run_message=str(getattr(dry_run_res, "message", "Dry-run preview succeeded.")),
            )

        except Exception as exc:
            logger.error(f"Dry-run preview failed: {exc}")
            raise RetrievalError(f"Copernicus Marine dry-run preview failed: {exc}") from exc

    def execute_retrieval(
        self,
        params: RetrievalParameters,
        job_id: str,
        custom_output_filename: Optional[str] = None,
    ) -> Path:
        """
        Executes actual subset download using copernicusmarine.subset().
        Guarantees that files are placed inside the configured staging directory.
        """
        dataset = self.validate_parameters(params)

        job_dir = self.staging_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        filename = None
        if custom_output_filename:
            filename = sanitize_filename(custom_output_filename)

        try:
            logger.info(
                f"[Job {job_id}] Initiating Copernicus subset: dataset_id={params.dataset_id}, "
                f"vars={params.variables}, bounds=[{params.minimum_longitude}, {params.minimum_latitude}, "
                f"{params.maximum_longitude}, {params.maximum_latitude}]"
            )

            res = copernicusmarine.subset(
                dataset_id=params.dataset_id,
                dataset_version=params.dataset_version or dataset.dataset_version,
                dataset_part=params.dataset_part or dataset.dataset_part,
                variables=params.variables,
                minimum_longitude=params.minimum_longitude,
                maximum_longitude=params.maximum_longitude,
                minimum_latitude=params.minimum_latitude,
                maximum_latitude=params.maximum_latitude,
                start_datetime=params.start_datetime,
                end_datetime=params.end_datetime,
                minimum_depth=params.minimum_depth,
                maximum_depth=params.maximum_depth,
                output_directory=job_dir,
                output_filename=filename,
                overwrite=True,
                dry_run=False,
                disable_progress_bar=True,
            )

            # Determine downloaded file path
            downloaded_file: Optional[Path] = None
            if hasattr(res, "file_path") and res.file_path:
                candidate = Path(res.file_path)
                if candidate.exists():
                    downloaded_file = candidate
            elif hasattr(res, "file_names") and res.file_names:
                candidate = job_dir / res.file_names[0]
                if candidate.exists():
                    downloaded_file = candidate

            if not downloaded_file:
                # Find any .nc file created in job_dir
                nc_files = list(job_dir.glob("*.nc"))
                if nc_files:
                    downloaded_file = nc_files[0]

            if not downloaded_file or not downloaded_file.exists():
                raise RetrievalError(f"Subset command reported success but no output file found in {job_dir}")

            logger.info(f"[Job {job_id}] Successfully retrieved: {downloaded_file} ({downloaded_file.stat().st_size} bytes)")
            return downloaded_file

        except Exception as exc:
            logger.error(f"[Job {job_id}] Subset retrieval failed: {exc}")
            raise RetrievalError(f"Copernicus Marine retrieval failed: {exc}") from exc


# Global retrieval service instance
retrieval_service = CopernicusRetrievalService()
