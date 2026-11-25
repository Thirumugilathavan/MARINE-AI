from typing import List, Optional, Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.modules.data_sources.copernicus.constants import (
    DEFAULT_INDIAN_OCEAN_BOUNDS,
    SUPPORTED_VARIABLES,
)
from app.modules.data_sources.copernicus.service import (
    search_catalogue,
    get_verified_datasets,
)
from app.modules.ingestion.copernicus_ingestion import CopernicusIngestionPipeline
from app.modules.validation.marine_validator import (
    BoundingBox,
    validate_cadence,
    validate_variables,
)

router = APIRouter(
    prefix="/api/v1/data-sources",
    tags=["Marine Data Sources"],
)


class IngestionRequest(BaseModel):
    cadence: Literal["nrt_six_hourly", "nrt_daily", "historical_daily"] = Field(
        default="nrt_daily",
        description="Temporal cadence for the Copernicus dataset",
    )
    variables: List[str] = Field(
        default=["thetao", "so", "uo", "vo"],
        description="List of oceanographic variables (thetao, so, uo, vo)",
    )
    minimum_longitude: float = Field(
        default=DEFAULT_INDIAN_OCEAN_BOUNDS["minimum_longitude"],
        ge=-180.0,
        le=180.0,
        description="Western bound longitude",
    )
    maximum_longitude: float = Field(
        default=DEFAULT_INDIAN_OCEAN_BOUNDS["maximum_longitude"],
        ge=-180.0,
        le=180.0,
        description="Eastern bound longitude",
    )
    minimum_latitude: float = Field(
        default=DEFAULT_INDIAN_OCEAN_BOUNDS["minimum_latitude"],
        ge=-90.0,
        le=90.0,
        description="Southern bound latitude",
    )
    maximum_latitude: float = Field(
        default=DEFAULT_INDIAN_OCEAN_BOUNDS["maximum_latitude"],
        ge=-90.0,
        le=90.0,
        description="Northern bound latitude",
    )
    start_datetime: Optional[str] = Field(
        default=None,
        description="ISO 8601 start datetime string (e.g. 2024-01-01T00:00:00)",
    )
    end_datetime: Optional[str] = Field(
        default=None,
        description="ISO 8601 end datetime string (e.g. 2024-01-02T00:00:00)",
    )
    minimum_depth: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Shallowest depth level in meters",
    )
    maximum_depth: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Deepest depth level in meters",
    )
    dry_run: bool = Field(
        default=False,
        description="Perform dry-run query without downloading files",
    )
    username: Optional[str] = Field(
        default=None,
        description="Copernicus Marine username (overrides environment variable)",
    )
    password: Optional[str] = Field(
        default=None,
        description="Copernicus Marine password (overrides environment variable)",
    )


class ValidationRequest(BaseModel):
    cadence: str = "nrt_daily"
    variables: List[str] = ["thetao", "so", "uo", "vo"]
    minimum_longitude: float = 30.0
    maximum_longitude: float = 120.0
    minimum_latitude: float = -30.0
    maximum_latitude: float = 30.0


@router.get("/copernicus/search")
def search_copernicus(
    keyword: str = Query(
        ...,
        min_length=2,
        description="Catalogue search term, e.g. thetao, salinity, chlorophyll",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Maximum number of products to return",
    ),
):
    try:
        return search_catalogue(keyword=keyword, limit=limit)

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Copernicus Marine catalogue request failed: {str(exc)}",
        ) from exc


@router.get("/copernicus/datasets")
def list_verified_datasets():
    """
    Returns catalogue details for all verified Copernicus Marine datasets,
    including cadences, update frequencies, supported variables, and default Indian Ocean bounds.
    """
    return get_verified_datasets()


@router.get("/copernicus/region")
def get_default_region():
    """
    Returns default Indian Ocean bounding box and spatial parameters.
    """
    return {
        "region_name": "Indian Ocean",
        "bounds": DEFAULT_INDIAN_OCEAN_BOUNDS,
        "spatial_resolution": "0.083 deg (~1/12 degree)",
        "supported_variables": list(SUPPORTED_VARIABLES.keys()),
    }


@router.post("/copernicus/validate")
def validate_request_parameters(request: ValidationRequest):
    """
    Validates cadence, variables, and bounding box parameters before triggering ingestion.
    """
    errors = []
    try:
        validate_cadence(request.cadence)
    except Exception as e:
        errors.append(str(e))

    try:
        validate_variables(request.variables)
    except Exception as e:
        errors.append(str(e))

    try:
        bbox = BoundingBox(
            minimum_longitude=request.minimum_longitude,
            maximum_longitude=request.maximum_longitude,
            minimum_latitude=request.minimum_latitude,
            maximum_latitude=request.maximum_latitude,
        )
        bbox.validate()
    except Exception as e:
        errors.append(str(e))

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "parameters": {
            "cadence": request.cadence,
            "variables": request.variables,
            "bounding_box": {
                "minimum_longitude": request.minimum_longitude,
                "maximum_longitude": request.maximum_longitude,
                "minimum_latitude": request.minimum_latitude,
                "maximum_latitude": request.maximum_latitude,
            },
        },
    }


@router.post("/copernicus/ingest")
def ingest_copernicus_data(request: IngestionRequest):
    """
    Triggers bounded Copernicus Marine data retrieval, validation, provenance tracking,
    and storage in SeaweedFS S3.
    """
    try:
        bbox = BoundingBox(
            minimum_longitude=request.minimum_longitude,
            maximum_longitude=request.maximum_longitude,
            minimum_latitude=request.minimum_latitude,
            maximum_latitude=request.maximum_latitude,
        )
        bbox.validate()
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    pipeline = CopernicusIngestionPipeline()
    try:
        result = pipeline.run_ingestion(
            cadence=request.cadence,
            variables=request.variables,
            bounding_box=bbox,
            start_datetime=request.start_datetime,
            end_datetime=request.end_datetime,
            minimum_depth=request.minimum_depth,
            maximum_depth=request.maximum_depth,
            username=request.username,
            password=request.password,
            dry_run=request.dry_run,
        )
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Copernicus ingestion pipeline error: {str(exc)}",
        ) from exc
