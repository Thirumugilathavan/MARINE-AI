"""
FastAPI Routes for WoRMS (World Register of Marine Species) Taxonomy Services.
Authoritative marine species taxonomy verification, accepted name resolution,
taxonomic hierarchy traversal, and synonym tracking.
"""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import MarineTaxonModel, TaxonSynonymModel
from app.modules.data_sources.worms.service import worms_service

router = APIRouter(prefix="/taxonomy", tags=["Taxonomy & WoRMS"])


@router.get("/worms/lookup/{scientific_name}")
def lookup_scientific_name(
    scientific_name: str,
    marine_only: bool = Query(True, description="Filter for strictly marine species"),
    db: Session = Depends(get_db),
):
    """
    Looks up scientific name in WoRMS Aphia register.
    Returns matched taxa records with accepted name verification and hierarchy.
    Utilizes PostgreSQL taxonomy cache to minimize external network requests.
    """
    clean_name = scientific_name.strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scientific name cannot be empty",
        )

    try:
        results = worms_service.lookup_by_name(clean_name, db=db, marine_only=marine_only)
        return {
            "query": clean_name,
            "count": len(results),
            "marine_only": marine_only,
            "results": results,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WoRMS lookup failed: {str(exc)}",
        )


@router.get("/worms/aphia/{aphia_id}")
def get_taxon_by_aphia_id(
    aphia_id: int,
    db: Session = Depends(get_db),
):
    """
    Retrieves full authoritative taxon record for an AphiaID.
    Resolves valid/accepted name, rank, kingdom down to species.
    """
    record = worms_service.get_by_aphia_id(aphia_id, db=db)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WoRMS taxon record for AphiaID {aphia_id} not found",
        )
    return record


@router.get("/worms/classification/{aphia_id}")
def get_taxonomic_classification(aphia_id: int):
    """
    Retrieves complete hierarchical classification tree from Kingdom to Species.
    """
    tree = worms_service.get_classification(aphia_id)
    if not tree:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Classification tree for AphiaID {aphia_id} not found",
        )
    return {
        "aphia_id": aphia_id,
        "classification": tree,
    }


@router.get("/worms/synonyms/{aphia_id}")
def get_taxon_synonyms(
    aphia_id: int,
    db: Session = Depends(get_db),
):
    """
    Retrieves all known junior synonyms and alternative names for a given AphiaID.
    """
    synonyms = worms_service.get_synonyms(aphia_id, db=db)
    return {
        "aphia_id": aphia_id,
        "count": len(synonyms),
        "synonyms": synonyms,
    }


@router.get("/taxa")
def list_local_taxa(
    kingdom: Optional[str] = Query(None, description="Filter by Kingdom"),
    phylum: Optional[str] = Query(None, description="Filter by Phylum"),
    status: Optional[str] = Query(None, description="Taxon status (e.g., accepted, unaccepted)"),
    search: Optional[str] = Query(None, description="Search scientific name substring"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Queries cached authoritative taxa persisted in PostgreSQL.
    Supports filtering by higher ranks and taxonomic verification status.
    """
    query = select(MarineTaxonModel)
    count_query = select(func.count(MarineTaxonModel.aphia_id))

    filters = []
    if kingdom:
        filters.append(func.lower(MarineTaxonModel.kingdom) == kingdom.lower())
    if phylum:
        filters.append(func.lower(MarineTaxonModel.phylum) == phylum.lower())
    if status:
        filters.append(func.lower(MarineTaxonModel.status) == status.lower())
    if search:
        filters.append(MarineTaxonModel.scientific_name.ilike(f"%{search}%"))

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = db.scalar(count_query) or 0
    records = db.execute(query.order_by(MarineTaxonModel.scientific_name).offset(offset).limit(limit)).scalars().all()

    taxa_data = []
    for r in records:
        taxa_data.append({
            "aphia_id": r.aphia_id,
            "scientific_name": r.scientific_name,
            "authority": r.authority,
            "rank": r.rank,
            "status": r.status,
            "valid_aphia_id": r.valid_aphia_id,
            "valid_name": r.valid_name,
            "kingdom": r.kingdom,
            "phylum": r.phylum,
            "class_name": r.class_name,
            "order_name": r.order_name,
            "family": r.family,
            "genus": r.genus,
            "is_marine": r.is_marine,
            "citation": r.citation,
            "lsid": r.lsid,
            "worms_url": r.worms_url,
        })

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "taxa": taxa_data,
    }
