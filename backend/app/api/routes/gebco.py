"""
GEBCO Bathymetry and Elevation API Routes.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.modules.data_sources.gebco.service import gebco_provider

router = APIRouter(prefix="/bathymetry", tags=["GEBCO Bathymetry"])


class PointDepthRequest(BaseModel):
    coordinates: List[List[float]] = Field(
        ...,
        description="List of [longitude, latitude] coordinate pairs",
        example=[[68.0, 12.0], [70.0, 14.0]]
    )


class PointDepthResponse(BaseModel):
    longitude: float
    latitude: float
    elevation_m: Optional[float]
    water_depth_m: Optional[float]
    is_ocean: bool
    source: str
    crs: str
    vertical_datum: str


@router.get("/depth", response_model=PointDepthResponse)
def get_point_depth(
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees"),
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees"),
):
    """
    Returns high-resolution seafloor water depth and elevation at specified coordinates
    from the official GEBCO / NOAA NCEI Global DEM Mosaic.
    """
    try:
        return gebco_provider.identify_point_depth(longitude=longitude, latitude=latitude)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GEBCO bathymetry lookup failed: {exc}")


@router.post("/profile", response_model=List[PointDepthResponse])
def get_bathymetry_profile(req: PointDepthRequest):
    """
    Returns bathymetric depth profile for a sequence of [lon, lat] coordinate pairs.
    """
    if len(req.coordinates) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 coordinates allowed per profile query.")

    results = []
    for coord in req.coordinates:
        if len(coord) != 2:
            raise HTTPException(status_code=422, detail="Each coordinate pair must be [longitude, latitude]")
        lon, lat = coord[0], coord[1]
        try:
            depth_info = gebco_provider.identify_point_depth(longitude=lon, latitude=lat)
            results.append(depth_info)
        except Exception as exc:
            results.append({
                "longitude": lon,
                "latitude": lat,
                "elevation_m": None,
                "water_depth_m": None,
                "is_ocean": False,
                "source": f"Error: {exc}",
                "crs": "EPSG:4326",
                "vertical_datum": "Mean Sea Level",
            })
    return results


@router.get("/tile")
def get_wms_tile(
    min_lon: float = Query(..., ge=-180.0, le=180.0),
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lon: float = Query(..., ge=-180.0, le=180.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    width: int = Query(256, ge=64, le=1024),
    height: int = Query(256, ge=64, le=1024),
    dataset_id: str = Query("gebco_2024_grid"),
):
    """
    Proxies an official GEBCO WMS bathymetric visualization tile (PNG).
    """
    import urllib.parse
    import httpx

    wms_layer = "GEBCO_LATEST_SUB_ICE_TOPO" if "sub_ice" in dataset_id else "GEBCO_LATEST"
    wms_params = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetMap",
        "layers": wms_layer,
        "styles": "",
        "crs": "EPSG:4326",
        "bbox": f"{min_lat},{min_lon},{max_lat},{max_lon}",
        "width": str(width),
        "height": str(height),
        "format": "image/png",
    }
    url = f"{gebco_provider.wms_url}?{urllib.parse.urlencode(wms_params)}"
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, verify=False) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"GEBCO WMS failed: {resp.text[:200]}")
            return Response(content=resp.content, media_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch GEBCO WMS tile: {exc}")
