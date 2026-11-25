"""
Metadata and scientific provenance module for Copernicus Marine observations.

Extracts CF conventions, attributes, coordinate limits, and builds
reproducible provenance records conforming to marine data standards.
"""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
import xarray as xr


def compute_sha256(file_path: Path | str) -> str:
    """Computes SHA-256 checksum of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def extract_netcdf_metadata(file_path: Path | str) -> Dict[str, Any]:
    """
    Extracts global attributes, coordinates extent, and variables metadata
    from a NetCDF file using xarray.
    """
    path = Path(file_path)
    with xr.open_dataset(path) as ds:
        attrs = dict(ds.attrs)
        dimensions = {str(k): int(v) for k, v in ds.sizes.items()}

        coordinates_extent: Dict[str, Dict[str, Any]] = {}
        for coord in ["longitude", "latitude", "time", "depth"]:
            if coord in ds.coords:
                vals = ds[coord].values
                if vals.size > 0:
                    coordinates_extent[coord] = {
                        "min": str(vals.min()),
                        "max": str(vals.max()),
                        "count": int(vals.size),
                    }

        variables_meta: Dict[str, Dict[str, Any]] = {}
        for var_name, data_var in ds.data_vars.items():
            variables_meta[str(var_name)] = {
                "standard_name": data_var.attrs.get("standard_name"),
                "long_name": data_var.attrs.get("long_name"),
                "units": data_var.attrs.get("units"),
                "dimensions": [str(d) for d in data_var.dims],
                "shape": list(data_var.shape),
            }

        return {
            "global_attributes": attrs,
            "dimensions": dimensions,
            "coordinates_extent": coordinates_extent,
            "variables_metadata": variables_meta,
            "cf_conventions": attrs.get("Conventions", "CF-1.8"),
            "producer": attrs.get("producer"),
            "institution": attrs.get("institution"),
            "title": attrs.get("title"),
            "licence": attrs.get("licence"),
            "source": attrs.get("source"),
            "copernicusmarine_version": attrs.get("copernicusmarine_version", "2.5.1"),
        }


def build_provenance_record(
    job_id: str,
    dataset_id: str,
    product_id: str,
    requested_variables: List[str],
    requested_spatial_extent: Dict[str, float],
    requested_time_interval: Dict[str, Any],
    file_path: Path | str,
    validation_report_id: Optional[str] = None,
    dataset_version: Optional[str] = "202406",
    dataset_part: Optional[str] = "default",
    provider_doi: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Constructs a standardized scientific provenance record dictionary.
    """
    nc_meta = extract_netcdf_metadata(file_path)
    checksum = compute_sha256(file_path)

    actual_time = nc_meta["coordinates_extent"].get("time", {})
    actual_lon = nc_meta["coordinates_extent"].get("longitude", {})
    actual_lat = nc_meta["coordinates_extent"].get("latitude", {})

    units = {
        var: meta.get("units", "unknown")
        for var, meta in nc_meta["variables_metadata"].items()
    }

    return {
        "job_id": job_id,
        "provider": "Copernicus Marine Service",
        "product_id": product_id,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "dataset_part": dataset_part,
        "provider_doi": provider_doi,
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        "requested_date_range": requested_time_interval,
        "actual_data_date_range": actual_time,
        "spatial_extent": {
            "requested": requested_spatial_extent,
            "actual": {
                "longitude": actual_lon,
                "latitude": actual_lat,
            },
        },
        "variables": requested_variables,
        "units": units,
        "processing_method": "copernicusmarine_subset_api",
        "source_licence": nc_meta.get("licence"),
        "toolbox_version": nc_meta.get("copernicusmarine_version", "2.5.1"),
        "sha256_checksum": checksum,
        "validation_report_id": validation_report_id,
    }
