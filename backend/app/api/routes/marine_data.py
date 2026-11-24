from fastapi import APIRouter, HTTPException, Query

from app.modules.data_sources.copernicus.service import search_catalogue


router = APIRouter(
    prefix="/api/v1/data-sources",
    tags=["Marine Data Sources"],
)


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