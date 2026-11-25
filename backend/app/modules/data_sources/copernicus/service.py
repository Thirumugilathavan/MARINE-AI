"""
Copernicus Marine Service data provider module.

Implements catalogue search and verified subset retrieval for Near-Real-Time (NRT)
six-hourly, NRT daily, and historical daily reanalysis oceanographic datasets.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
import copernicusmarine

from app.core.config import settings
from app.modules.data_sources.copernicus.constants import (
    DEFAULT_INDIAN_OCEAN_BOUNDS,
    CADENCE_DATASET_MAP,
    SUPPORTED_VARIABLES,
)
from app.modules.validation.marine_validator import (
    BoundingBox,
    validate_cadence,
    validate_variables,
)

logger = logging.getLogger(__name__)


def search_catalogue(keyword: str, limit: int = 10) -> Dict[str, Any]:
    """
    Search the Copernicus Marine catalogue.

    Args:
        keyword: Search term, such as thetao, salinity, or chlorophyll.
        limit: Maximum number of products to return.

    Returns:
        A list of catalogue products.
    """
    result = copernicusmarine.describe(
        contains=[keyword],
        disable_progress_bar=True,
    )

    products = []
    for product in result.products[:limit]:
        products.append(
            {
                "product_id": product.product_id,
                "title": product.title,
            }
        )

    return {
        "provider": "Copernicus Marine",
        "query": keyword,
        "total_found": len(result.products),
        "returned": len(products),
        "products": products,
    }


def get_verified_datasets() -> Dict[str, Any]:
    """
    Returns catalogue details for all verified Copernicus Marine datasets supported by the platform.
    """
    return {
        "provider": "Copernicus Marine Service",
        "target_region": "Indian Ocean",
        "default_bounding_box": DEFAULT_INDIAN_OCEAN_BOUNDS,
        "supported_variables": SUPPORTED_VARIABLES,
        "cadences": CADENCE_DATASET_MAP,
    }


def plan_retrieval(cadence: str, variables: List[str]) -> List[Dict[str, Any]]:
    """
    Resolves the minimal set of dataset requests needed to fetch the requested variables for a given cadence.

    Returns:
        List of dicts: [{"dataset_id": ..., "variables": [...]}, ...]
    """
    validate_cadence(cadence)
    validate_variables(variables)

    cadence_info = CADENCE_DATASET_MAP[cadence]
    var_map = cadence_info["variable_datasets"]

    # Group variables by target dataset_id
    dataset_to_vars: Dict[str, List[str]] = {}
    for var in variables:
        ds_id = var_map[var]
        dataset_to_vars.setdefault(ds_id, []).append(var)

    plan = []
    for ds_id, var_list in dataset_to_vars.items():
        plan.append({
            "dataset_id": ds_id,
            "variables": var_list,
            "cadence": cadence,
        })

    return plan


def retrieve_copernicus_subset(
    cadence: str,
    variables: List[str],
    bounding_box: Optional[BoundingBox] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    minimum_depth: Optional[float] = None,
    maximum_depth: Optional[float] = None,
    output_directory: Optional[Path] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Executes bounded subset retrieval for Copernicus Marine data.

    Enforces strict coordinate bounding to prevent downloading global datasets.
    """
    validate_cadence(cadence)
    validate_variables(variables)

    bbox = bounding_box or BoundingBox.default_indian_ocean()
    bbox.validate()

    user = username or settings.copernicus_marine_username
    pwd = password or settings.copernicus_marine_password

    # Check credentials if live download is requested
    if not dry_run and not (user and pwd):
        return {
            "status": "authentication_required",
            "message": (
                "Copernicus Marine Service requires free account credentials to download/subset datasets. "
                "Configure COPERNICUS_MARINE_USERNAME and COPERNICUS_MARINE_PASSWORD in backend/.env "
                "or register at https://data.marine.copernicus.eu/register"
            ),
            "cadence": cadence,
            "variables": variables,
            "bounding_box": {
                "min_lon": bbox.minimum_longitude,
                "max_lon": bbox.maximum_longitude,
                "min_lat": bbox.minimum_latitude,
                "max_lat": bbox.maximum_latitude,
            },
            "downloaded_files": [],
        }

    plan = plan_retrieval(cadence, variables)
    downloaded_files: List[Dict[str, Any]] = []

    out_dir = output_directory or (Path.cwd() / "dataset-staging" / "copernicus")
    out_dir.mkdir(parents=True, exist_ok=True)

    for item in plan:
        dataset_id = item["dataset_id"]
        req_vars = item["variables"]

        try:
            logger.info(
                f"Requesting Copernicus subset: dataset_id={dataset_id}, vars={req_vars}, "
                f"bbox=[{bbox.minimum_longitude}, {bbox.minimum_latitude}, {bbox.maximum_longitude}, {bbox.maximum_latitude}]"
            )

            response = copernicusmarine.subset(
                dataset_id=dataset_id,
                variables=req_vars,
                minimum_longitude=bbox.minimum_longitude,
                maximum_longitude=bbox.maximum_longitude,
                minimum_latitude=bbox.minimum_latitude,
                maximum_latitude=bbox.maximum_latitude,
                minimum_depth=minimum_depth,
                maximum_depth=maximum_depth,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                output_directory=out_dir,
                username=user,
                password=pwd,
                overwrite=True,
                dry_run=dry_run,
                disable_progress_bar=True,
            )

            downloaded_files.append({
                "dataset_id": dataset_id,
                "variables": req_vars,
                "status": "success",
                "response": str(response),
            })

        except Exception as exc:
            logger.error(f"Failed subset for dataset {dataset_id}: {exc}")
            downloaded_files.append({
                "dataset_id": dataset_id,
                "variables": req_vars,
                "status": "failed",
                "error": str(exc),
            })

    overall_status = "success" if all(f["status"] == "success" for f in downloaded_files) else "partial_failure"

    return {
        "status": overall_status,
        "cadence": cadence,
        "variables": variables,
        "bounding_box": {
            "min_lon": bbox.minimum_longitude,
            "max_lon": bbox.maximum_longitude,
            "min_lat": bbox.minimum_latitude,
            "max_lat": bbox.maximum_latitude,
        },
        "temporal_range": {
            "start": start_datetime,
            "end": end_datetime,
        },
        "depth_range": {
            "min_depth": minimum_depth,
            "max_depth": maximum_depth,
        },
        "downloaded_files": downloaded_files,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
