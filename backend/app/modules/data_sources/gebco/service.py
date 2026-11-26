"""
GEBCO (General Bathymetric Chart of the Oceans) Data Provider.

Integrates official GEBCO WMS services (IHO/IOC-UNESCO) and NOAA NCEI DEM
Global Mosaic services for global high-resolution seafloor bathymetry and elevation.
"""

from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re
import time
from typing import Dict, List, Optional, Any
import urllib.parse
import uuid

import httpx
import numpy as np

from app.modules.data_sources.base import (
    BaseMarineProvider,
    ProviderMetadata,
    ProviderDatasetMeta,
    UnifiedRetrievalParams,
    UnifiedPreviewResult,
    UnifiedRetrievalResult,
    UnifiedValidationResult,
    UnifiedProvenanceInfo,
    VariableStatsSummary,
)
from app.modules.data_sources.copernicus.exceptions import (
    DatasetNotFoundError,
    InvalidVariableError,
    InvalidBoundsError,
    RetrievalError,
)

logger = logging.getLogger(__name__)

GEBCO_WMS_URL = "https://wms.gebco.net/mapserv"
NCEI_DEM_MOSAIC_URL = "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_global_mosaic/ImageServer"

GEBCO_VERIFIED_DATASETS: Dict[str, ProviderDatasetMeta] = {
    "gebco_2024_grid": ProviderDatasetMeta(
        provider_id="gebco",
        dataset_id="gebco_2024_grid",
        product_id="GEBCO_2024_GLOBAL_15ARCSEC",
        product_title="GEBCO 2024 Global Bathymetric and Topographic Grid",
        dataset_description=(
            "The GEBCO 2024 Grid is a continuous, global terrain model for ocean and land, "
            "providing elevation and depth data at a 15 arc-second spatial interval (~450m at the equator). "
            "Produced by the Nippon Foundation-GEBCO Seabed 2030 Project."
        ),
        available_variables=["elevation", "depth"],
        variable_metadata={
            "elevation": {
                "standard_name": "surface_altitude",
                "units": "m",
                "long_name": "Elevation/Bathymetry relative to Mean Sea Level (negative for depth)",
                "valid_min": -11000.0,
                "valid_max": 8848.0,
            },
            "depth": {
                "standard_name": "sea_floor_depth_below_sea_surface",
                "units": "m",
                "long_name": "Water depth below Mean Sea Level (positive value)",
                "valid_min": 0.0,
                "valid_max": 11000.0,
            },
        },
        temporal_resolution="static_annual_release",
        spatial_resolution="15 arc-second (~450 m)",
        data_type="bathymetric_elevation_grid",
        spatial_coverage={"min_lon": -180.0, "max_lon": 180.0, "min_lat": -90.0, "max_lat": 90.0},
        depth_levels_count=1,
        depth_min=0.0,
        depth_max=11000.0,
        time_coverage_start="2024-01-01T00:00:00Z",
        source_documentation="https://www.gebco.net/data_and_products/gridded_bathymetry_data/",
        licence_information="GEBCO Open Data Policy (CC-BY 4.0 compatible, free with attribution)",
        verification_status="verified",
    ),
    "gebco_sub_ice_topo": ProviderDatasetMeta(
        provider_id="gebco",
        dataset_id="gebco_sub_ice_topo",
        product_id="GEBCO_2024_SUB_ICE_TOPO",
        product_title="GEBCO 2024 Sub-Ice Topography and Bathymetry Grid",
        dataset_description=(
            "GEBCO 2024 Grid showing bed topography under the Antarctic and Greenland ice sheets, "
            "incorporating BedMachine Antarctica and Greenland datasets."
        ),
        available_variables=["elevation", "depth"],
        variable_metadata={
            "elevation": {
                "standard_name": "surface_altitude",
                "units": "m",
                "long_name": "Bedrock elevation relative to Mean Sea Level",
                "valid_min": -11000.0,
                "valid_max": 8848.0,
            },
            "depth": {
                "standard_name": "sea_floor_depth_below_sea_surface",
                "units": "m",
                "long_name": "Water depth below Mean Sea Level",
                "valid_min": 0.0,
                "valid_max": 11000.0,
            },
        },
        temporal_resolution="static_annual_release",
        spatial_resolution="15 arc-second (~450 m)",
        data_type="bathymetric_elevation_grid",
        spatial_coverage={"min_lon": -180.0, "max_lon": 180.0, "min_lat": -90.0, "max_lat": 90.0},
        depth_levels_count=1,
        depth_min=0.0,
        depth_max=11000.0,
        time_coverage_start="2024-01-01T00:00:00Z",
        source_documentation="https://www.gebco.net/data_and_products/gridded_bathymetry_data/",
        licence_information="GEBCO Open Data Policy (CC-BY 4.0 compatible)",
        verification_status="verified",
    ),
}


class GEBCOBathymetryProvider(BaseMarineProvider):
    """
    GEBCO implementation of BaseMarineProvider connecting to official GEBCO WMS
    and NOAA NCEI DEM Global Mosaic raster services.
    """

    def __init__(
        self,
        wms_url: str = GEBCO_WMS_URL,
        dem_url: str = NCEI_DEM_MOSAIC_URL,
        timeout: float = 30.0,
    ):
        self.wms_url = wms_url.rstrip("/")
        self.dem_url = dem_url.rstrip("/")
        self.timeout = timeout
        self._metadata = ProviderMetadata(
            provider_id="gebco",
            name="General Bathymetric Chart of the Oceans",
            organization="IHO / IOC-UNESCO GEBCO Guiding Committee / BODC / NOAA NCEI",
            base_url=self.wms_url,
            documentation_url="https://www.gebco.net/data_and_products/gridded_bathymetry_data/",
            access_method="ogc_wms_and_dem_imageserver",
            authentication_required=False,
            auth_description="Public domain / Open access bathymetry under IHO-IOC GEBCO policy.",
            status="operational",
            supported_formats=["GeoTIFF", "PNG", "JSON"],
            rate_limits_info="Standard institutional fair use policy",
            licence_info="GEBCO Open Data Policy (CC-BY 4.0 compatible)",
        )

    def metadata(self) -> ProviderMetadata:
        return self._metadata

    def list_datasets(self) -> List[ProviderDatasetMeta]:
        return list(GEBCO_VERIFIED_DATASETS.values())

    def get_dataset(self, dataset_id: str) -> ProviderDatasetMeta:
        if dataset_id not in GEBCO_VERIFIED_DATASETS:
            raise DatasetNotFoundError(
                f"Dataset '{dataset_id}' not found in GEBCO provider registry. "
                f"Available: {list(GEBCO_VERIFIED_DATASETS.keys())}"
            )
        return GEBCO_VERIFIED_DATASETS[dataset_id]

    def search_catalogue(self, query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        results = []
        q = query.lower()
        for ds in GEBCO_VERIFIED_DATASETS.values():
            if not q or q in ds.dataset_id.lower() or q in ds.product_title.lower() or q in ds.dataset_description.lower():
                results.append({
                    "product_id": ds.product_id,
                    "dataset_id": ds.dataset_id,
                    "title": ds.product_title,
                    "description": ds.dataset_description,
                    "variables": ds.available_variables,
                    "spatial_resolution": ds.spatial_resolution,
                    "licence": ds.licence_information,
                })
        return results[:limit]

    def validate_parameters(self, params: UnifiedRetrievalParams) -> UnifiedRetrievalParams:
        self.get_dataset(params.dataset_id)

        # Coordinate bounds
        if not (-180.0 <= params.minimum_longitude <= 180.0):
            raise InvalidBoundsError(f"minimum_longitude {params.minimum_longitude} out of range [-180, 180]")
        if not (-180.0 <= params.maximum_longitude <= 180.0):
            raise InvalidBoundsError(f"maximum_longitude {params.maximum_longitude} out of range [-180, 180]")
        if params.minimum_longitude >= params.maximum_longitude:
            raise InvalidBoundsError(
                f"minimum_longitude ({params.minimum_longitude}) must be < maximum_longitude ({params.maximum_longitude})"
            )

        if not (-90.0 <= params.minimum_latitude <= 90.0):
            raise InvalidBoundsError(f"minimum_latitude {params.minimum_latitude} out of range [-90, 90]")
        if not (-90.0 <= params.maximum_latitude <= 90.0):
            raise InvalidBoundsError(f"maximum_latitude {params.maximum_latitude} out of range [-90, 90]")
        if params.minimum_latitude >= params.maximum_latitude:
            raise InvalidBoundsError(
                f"minimum_latitude ({params.minimum_latitude}) must be < maximum_latitude ({params.maximum_latitude})"
            )

        # Variables
        if params.variables:
            for v in params.variables:
                if v not in ["elevation", "depth"]:
                    raise InvalidVariableError(f"Variable '{v}' not supported by GEBCO. Choose 'elevation' or 'depth'.")
        else:
            params.variables = ["elevation", "depth"]

        return params

    def preview(self, params: UnifiedRetrievalParams) -> UnifiedPreviewResult:
        self.validate_parameters(params)

        d_lon = params.maximum_longitude - params.minimum_longitude
        d_lat = params.maximum_latitude - params.minimum_latitude
        bbox_area = round(d_lon * d_lat, 4)

        # At 15 arc-sec (~240 points per degree)
        pts_lon = max(int(d_lon * 240), 1)
        pts_lat = max(int(d_lat * 240), 1)
        est_pts = pts_lon * pts_lat
        est_mb = round((est_pts * 4) / (1024 * 1024), 4)  # 4 bytes per float32 pixel

        return UnifiedPreviewResult(
            request_id=str(uuid.uuid4()),
            provider_id="gebco",
            dataset_id=params.dataset_id,
            estimated_size_mb=est_mb,
            estimated_total_points=est_pts,
            bounding_box_area_deg2=bbox_area,
            duration_days=1.0,  # Static bathymetry grid
            status="success",
            message=(
                f"GEBCO preview: Bounding box {params.minimum_longitude}°E to {params.maximum_longitude}°E, "
                f"{params.minimum_latitude}°N to {params.maximum_latitude}°N. "
                f"Area: {bbox_area} deg² (~{pts_lon}x{pts_lat} cells at 15 arc-sec resolution, ~{est_mb} MB)."
            ),
            selected_extent={
                "min_lon": params.minimum_longitude,
                "max_lon": params.maximum_longitude,
                "min_lat": params.minimum_latitude,
                "max_lat": params.maximum_latitude,
                "crs": "EPSG:4326",
                "vertical_datum": "Mean Sea Level (m)",
            },
            variables=params.variables,
        )

    def retrieve(
        self,
        params: UnifiedRetrievalParams,
        job_id: str,
        staging_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        format_type: str = "GeoTIFF",
        **kwargs,
    ) -> UnifiedRetrievalResult:
        """
        Retrieves a bounded bathymetry raster from the official DEM / GEBCO service.
        Saves as a GeoTIFF (.tif) or WMS rendered PNG tile.
        """
        self.validate_parameters(params)

        target_dir = staging_dir or output_dir or Path("dataset-staging/gebco")
        job_dir = target_dir / job_id if job_id not in str(target_dir) else target_dir
        job_dir.mkdir(parents=True, exist_ok=True)

        is_png = (format_type.lower() == "png")
        ext = ".png" if is_png else ".tif"
        file_format = "PNG" if is_png else "GeoTIFF"

        filename = params.output_filename or f"gebco_{params.dataset_id}_{job_id[:8]}{ext}"
        clean_name = re.sub(r"[^\w\-.]", "_", Path(filename).name)
        if not clean_name.endswith(ext):
            clean_name += ext
        target_path = job_dir / clean_name

        max_retries = 3
        backoff_seconds = 2.0
        resp = None

        if is_png:
            # Official GEBCO WMS GetMap endpoint
            wms_layer = "GEBCO_LATEST_SUB_ICE_TOPO" if "sub_ice" in params.dataset_id else "GEBCO_LATEST"
            wms_params = {
                "service": "WMS",
                "version": "1.3.0",
                "request": "GetMap",
                "layers": wms_layer,
                "styles": "",
                "crs": "EPSG:4326",
                "bbox": f"{params.minimum_latitude},{params.minimum_longitude},{params.maximum_latitude},{params.maximum_longitude}",
                "width": "512",
                "height": "512",
                "format": "image/png",
            }
            download_url = f"{self.wms_url}?{urllib.parse.urlencode(wms_params)}"
        else:
            # NOAA NCEI Global DEM Mosaic ImageServer (returns raw 32-bit float GeoTIFF)
            export_params = {
                "bbox": f"{params.minimum_longitude},{params.minimum_latitude},{params.maximum_longitude},{params.maximum_latitude}",
                "bboxSR": "4326",
                "imageSR": "4326",
                "size": "256,256",
                "format": "tiff",
                "pixelType": "F32",
                "f": "image",
            }
            download_url = f"{self.dem_url}/exportImage?{urllib.parse.urlencode(export_params)}"

        logger.info(f"[Job {job_id}] Requesting GEBCO bathymetry from: {download_url}")

        with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            for attempt in range(1, max_retries + 1):
                try:
                    resp = client.get(download_url)
                    if resp.status_code == 200 and len(resp.content) > 100:
                        break
                    elif resp.status_code in (502, 503, 504) and attempt < max_retries:
                        logger.warning(
                            f"[Job {job_id}] GEBCO endpoint returned {resp.status_code} (attempt {attempt}/{max_retries}). Retrying..."
                        )
                        time.sleep(backoff_seconds)
                        backoff_seconds *= 2
                    else:
                        raise RetrievalError(f"GEBCO request failed with HTTP {resp.status_code}: {resp.text[:300]}")
                except (httpx.TransportError, httpx.TimeoutException) as exc:
                    if attempt < max_retries:
                        logger.warning(f"[Job {job_id}] GEBCO transport error: {exc}. Retrying...")
                        time.sleep(backoff_seconds)
                        backoff_seconds *= 2
                    else:
                        raise RetrievalError(f"GEBCO network error after {max_retries} attempts: {exc}") from exc

            if resp is None or resp.status_code != 200:
                raise RetrievalError(f"GEBCO retrieval failed after {max_retries} attempts.")

            target_path.write_bytes(resp.content)

        file_size = target_path.stat().st_size
        sha256_hash = hashlib.sha256(resp.content).hexdigest()

        return UnifiedRetrievalResult(
            job_id=job_id,
            provider_id="gebco",
            dataset_id=params.dataset_id,
            file_path=target_path,
            file_format=file_format,
            file_size_bytes=file_size,
            sha256_checksum=sha256_hash,
            raw_metadata={
                "download_url": download_url,
                "format": file_format,
                "bbox": [params.minimum_longitude, params.minimum_latitude, params.maximum_longitude, params.maximum_latitude],
                "crs": "EPSG:4326",
                "vertical_datum": "Mean Sea Level (meters)",
            },
        )

    def identify_point_depth(self, longitude: float, latitude: float) -> Dict[str, Any]:
        """Queries the point elevation/bathymetry depth at exact coordinates."""
        ident_params = {
            "geometry": f"{{\"x\":{longitude},\"y\":{latitude}}}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "f": "json",
        }
        url = f"{self.dem_url}/identify?{urllib.parse.urlencode(ident_params)}"
        with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                raise RetrievalError(f"Point identify failed with HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            raw_val = data.get("value")
            elevation = float(raw_val) if raw_val is not None else None
            depth = abs(elevation) if (elevation is not None and elevation < 0) else 0.0

            return {
                "longitude": longitude,
                "latitude": latitude,
                "elevation_m": elevation,
                "water_depth_m": depth,
                "is_ocean": (elevation is not None and elevation < 0),
                "source": "GEBCO / NOAA NCEI Global DEM Mosaic",
                "crs": "EPSG:4326",
                "vertical_datum": "Mean Sea Level",
            }

    def validate_data(
        self,
        file_path: Path,
        expected_params: Optional[UnifiedRetrievalParams] = None,
        **kwargs,
    ) -> UnifiedValidationResult:
        path = Path(file_path)
        dataset_id = expected_params.dataset_id if expected_params else "gebco_2024_grid"

        if not path.exists() or path.stat().st_size == 0:
            return UnifiedValidationResult(
                file_path=str(path),
                provider_id="gebco",
                dataset_id=dataset_id,
                status="failed",
                is_valid=False,
                errors=[f"File does not exist or is empty: {path}"],
            )

        content = path.read_bytes()
        file_size = len(content)
        warnings: List[str] = []
        errors: List[str] = []

        is_tiff = content[:4] in (b"II*\x00", b"MM\x00*")
        is_png = content.startswith(b"\x89PNG\r\n\x1a\n")

        if not (is_tiff or is_png):
            errors.append(f"Unrecognized raster signature for GEBCO file {path.name}")

        dims = {"file_size_bytes": file_size}
        var_stats: Dict[str, VariableStatsSummary] = {}

        if is_tiff:
            try:
                # If Pillow is available, inspect image metadata
                from PIL import Image
                with Image.open(path) as img:
                    dims["width"] = img.width
                    dims["height"] = img.height
                    dims["mode"] = img.mode

                var_stats["elevation"] = VariableStatsSummary(
                    variable_name="elevation",
                    standard_name="surface_altitude",
                    units="m",
                    total_points=dims.get("width", 256) * dims.get("height", 256),
                    valid_points=dims.get("width", 256) * dims.get("height", 256),
                )
            except Exception as e:
                warnings.append(f"TIFF raster inspection note: {e}")
        elif is_png:
            var_stats["elevation_map_tile"] = VariableStatsSummary(
                variable_name="elevation_map_tile",
                standard_name="surface_altitude_visualization",
                units="pixel_rgba",
                total_points=512 * 512,
                valid_points=512 * 512,
            )

        status = "passed" if not errors else "failed"
        if warnings and status == "passed":
            status = "warnings"

        return UnifiedValidationResult(
            file_path=str(path),
            provider_id="gebco",
            dataset_id=dataset_id,
            status=status,
            is_valid=(len(errors) == 0),
            dimensions=dims,
            coordinates_summary={
                "crs": "EPSG:4326",
                "vertical_datum": "Mean Sea Level",
                "spatial_bounds": (
                    {
                        "min_lon": expected_params.minimum_longitude,
                        "max_lon": expected_params.maximum_longitude,
                        "min_lat": expected_params.minimum_latitude,
                        "max_lat": expected_params.maximum_latitude,
                    }
                    if expected_params
                    else {}
                ),
            },
            variable_stats=var_stats,
            warnings=warnings,
            errors=errors,
        )

    def generate_provenance(
        self,
        retrieval_result: Any,
        validation_result: Optional[UnifiedValidationResult] = None,
        params: Optional[UnifiedRetrievalParams] = None,
        job_id: Optional[str] = None,
        **kwargs,
    ) -> UnifiedProvenanceInfo:
        effective_job_id = job_id or (retrieval_result.job_id if hasattr(retrieval_result, "job_id") else "gebco-job")
        dataset_id = params.dataset_id if params else (retrieval_result.dataset_id if hasattr(retrieval_result, "dataset_id") else "gebco_2024_grid")
        dataset = self.get_dataset(dataset_id)

        spat_ext = (validation_result.coordinates_summary if validation_result else {}) or {}

        return UnifiedProvenanceInfo(
            job_id=effective_job_id,
            provider="General Bathymetric Chart of the Oceans (GEBCO)",
            product_id=dataset.product_id,
            dataset_id=dataset_id,
            dataset_version="2024",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            requested_date_range={"start": "2024-01-01T00:00:00Z", "end": "2024-12-31T23:59:59Z"},
            actual_data_date_range={"release_year": "2024"},
            spatial_extent=spat_ext,
            variables=params.variables if params else list(dataset.available_variables),
            units={"elevation": "m", "depth": "m"},
            processing_method="ogc_wms_and_dem_imageserver",
            source_licence=dataset.licence_information,
            provider_doi="https://doi.org/10.5285/1c44ce99-0300-56ff-e063-7086abc0ea0f",
            toolbox_version="MARINE-AI-Unified-1.0",
            sha256_checksum=retrieval_result.sha256_checksum if hasattr(retrieval_result, "sha256_checksum") else "",
        )


gebco_provider = GEBCOBathymetryProvider()
