"""
World Register of Marine Species (WoRMS) Taxonomy Service.

Integrates the official WoRMS Aphia REST API for authoritative scientific name
verification, accepted name resolution, taxonomic hierarchy, and synonym tracking.
"""

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Any
import urllib.parse

import httpx
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from app.database.models import (
    MarineTaxonModel,
    TaxonSynonymModel,
    TaxonomyLookupCacheModel,
)

logger = logging.getLogger(__name__)

WORMS_API_BASE = "https://www.marinespecies.org/rest"


class WoRMSTaxonomyService:
    """Official WoRMS Aphia REST API client with relational PostgreSQL caching."""

    def __init__(self, base_url: str = WORMS_API_BASE, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def lookup_by_name(
        self,
        scientific_name: str,
        db: Optional[Session] = None,
        marine_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Looks up scientific name in WoRMS.
        Checks local database cache first; on miss, queries live API and persists results.
        """
        clean_name = scientific_name.strip()
        if not clean_name:
            return []

        # 1. Check local cache if DB session is provided
        if db:
            cached = db.execute(
                select(TaxonomyLookupCacheModel).where(
                    TaxonomyLookupCacheModel.query_name == clean_name.lower()
                )
            ).scalar_one_or_none()

            if cached and cached.raw_result:
                cached_items = cached.raw_result.get("records", [])
                if cached_items:
                    return cached_items

        # 2. Query official WoRMS REST API
        encoded_name = urllib.parse.quote(clean_name)
        url = f"{self.base_url}/AphiaRecordsByName/{encoded_name}"
        params = {"marine_only": str(marine_only).lower(), "like": "false"}

        records = []
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    records = resp.json()
                elif resp.status_code == 204 or resp.status_code == 404:
                    records = []
                else:
                    logger.warning(f"WoRMS lookup for '{clean_name}' returned status {resp.status_code}")
        except Exception as exc:
            logger.error(f"WoRMS API request error: {exc}")
            raise

        # 3. Normalize records
        normalized = []
        for r in records:
            norm = {
                "aphia_id": r.get("AphiaID"),
                "scientific_name": r.get("scientificname"),
                "authority": r.get("authority"),
                "rank": r.get("rank"),
                "status": r.get("status"),
                "valid_aphia_id": r.get("valid_AphiaID"),
                "valid_name": r.get("valid_name"),
                "valid_authority": r.get("valid_authority"),
                "kingdom": r.get("kingdom"),
                "phylum": r.get("phylum"),
                "class_name": r.get("class"),
                "order_name": r.get("order"),
                "family": r.get("family"),
                "genus": r.get("genus"),
                "citation": r.get("citation"),
                "lsid": r.get("lsid"),
                "url": r.get("url"),
                "is_marine": bool(r.get("isMarine", 1)),
                "raw_record": r,
            }
            normalized.append(norm)

            # Persist to marine_taxa table if DB provided
            if db and norm["aphia_id"]:
                self._upsert_taxon(db, norm)

        # 4. Save to lookup cache
        if db:
            match_status = "exact_match" if normalized else "not_found"
            first_aphia = normalized[0]["aphia_id"] if normalized else None
            cache_entry = TaxonomyLookupCacheModel(
                query_name=clean_name.lower(),
                aphia_id=first_aphia,
                match_status=match_status,
                raw_result={"records": normalized, "timestamp": datetime.now(timezone.utc).isoformat()},
            )
            db.merge(cache_entry)
            db.commit()

        return normalized

    def get_by_aphia_id(self, aphia_id: int, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
        """Retrieves authoritative AphiaRecord by AphiaID."""
        # Check database
        if db:
            existing = db.execute(
                select(MarineTaxonModel).where(MarineTaxonModel.aphia_id == aphia_id)
            ).scalar_one_or_none()
            if existing:
                return {
                    "aphia_id": existing.aphia_id,
                    "scientific_name": existing.scientific_name,
                    "authority": existing.authority,
                    "rank": existing.rank,
                    "status": existing.status,
                    "valid_aphia_id": existing.valid_aphia_id,
                    "valid_name": existing.valid_name,
                    "kingdom": existing.kingdom,
                    "phylum": existing.phylum,
                    "class_name": existing.class_name,
                    "order_name": existing.order_name,
                    "family": existing.family,
                    "genus": existing.genus,
                    "citation": existing.citation,
                    "lsid": existing.lsid,
                    "url": existing.worms_url,
                }

        # Query live API
        url = f"{self.base_url}/AphiaRecordByAphiaID/{aphia_id}"
        with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                raw = resp.json()
                norm = {
                    "aphia_id": raw.get("AphiaID"),
                    "scientific_name": raw.get("scientificname"),
                    "authority": raw.get("authority"),
                    "rank": raw.get("rank"),
                    "status": raw.get("status"),
                    "valid_aphia_id": raw.get("valid_AphiaID"),
                    "valid_name": raw.get("valid_name"),
                    "valid_authority": raw.get("valid_authority"),
                    "kingdom": raw.get("kingdom"),
                    "phylum": raw.get("phylum"),
                    "class_name": raw.get("class"),
                    "order_name": raw.get("order"),
                    "family": raw.get("family"),
                    "genus": raw.get("genus"),
                    "citation": raw.get("citation"),
                    "lsid": raw.get("lsid"),
                    "url": raw.get("url"),
                    "is_marine": bool(raw.get("isMarine", 1)),
                    "raw_record": raw,
                }
                if db:
                    self._upsert_taxon(db, norm)
                    db.commit()
                return norm
            return None

    def get_classification(self, aphia_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves complete taxonomic classification tree for an AphiaID."""
        url = f"{self.base_url}/AphiaClassificationByAphiaID/{aphia_id}"
        with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return resp.json()
            return None

    def get_synonyms(self, aphia_id: int, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """Retrieves all junior synonyms and alternative names for an AphiaID."""
        url = f"{self.base_url}/AphiaSynonymsByAphiaID/{aphia_id}"
        synonyms = []
        with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                for s in data:
                    syn = {
                        "aphia_id": aphia_id,
                        "synonym_aphia_id": s.get("AphiaID"),
                        "synonym_name": s.get("scientificname"),
                        "synonym_authority": s.get("authority"),
                        "synonym_status": s.get("status", "unaccepted"),
                    }
                    synonyms.append(syn)
                    if db:
                        syn_model = TaxonSynonymModel(
                            aphia_id=aphia_id,
                            synonym_aphia_id=syn["synonym_aphia_id"],
                            synonym_name=syn["synonym_name"],
                            synonym_authority=syn["synonym_authority"],
                            synonym_status=syn["synonym_status"],
                        )
                        db.add(syn_model)
                if db:
                    db.commit()
        return synonyms

    def _upsert_taxon(self, db: Session, data: Dict[str, Any]) -> MarineTaxonModel:
        """Internal helper to upsert taxon entity into PostgreSQL."""
        existing = db.execute(
            select(MarineTaxonModel).where(MarineTaxonModel.aphia_id == data["aphia_id"])
        ).scalar_one_or_none()

        if existing:
            existing.scientific_name = data["scientific_name"]
            existing.status = data["status"]
            existing.valid_aphia_id = data.get("valid_aphia_id")
            existing.valid_name = data.get("valid_name")
            return existing

        taxon = MarineTaxonModel(
            aphia_id=data["aphia_id"],
            scientific_name=data["scientific_name"],
            authority=data.get("authority"),
            rank=data.get("rank") or "Species",
            status=data.get("status") or "accepted",
            valid_aphia_id=data.get("valid_aphia_id"),
            valid_name=data.get("valid_name"),
            valid_authority=data.get("valid_authority"),
            kingdom=data.get("kingdom"),
            phylum=data.get("phylum"),
            class_name=data.get("class_name"),
            order_name=data.get("order_name"),
            family=data.get("family"),
            genus=data.get("genus"),
            is_marine=data.get("is_marine", True),
            citation=data.get("citation"),
            lsid=data.get("lsid"),
            worms_url=data.get("url"),
            raw_aphia_record=data.get("raw_record", {}),
        )
        db.add(taxon)
        return taxon


worms_service = WoRMSTaxonomyService()
