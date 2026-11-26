"""
Marine Biodiversity Integration Services (OBIS and GBIF).

Integrates the Ocean Biodiversity Information System (OBIS) and Global Biodiversity
Information Facility (GBIF) for marine species occurrences, spatial indexing in PostGIS,
and cross-provider duplicate reconciliation.
"""

from datetime import datetime, timezone
import hashlib
import logging
from math import radians, cos, sin, asin, sqrt
from typing import Dict, List, Optional, Any, Tuple
import urllib.parse
import uuid

import httpx
from sqlalchemy import select, and_, func, or_
from sqlalchemy.orm import Session

from app.database.models import MarineSpeciesOccurrenceModel

logger = logging.getLogger(__name__)

OBIS_API_BASE = "https://api.obis.org/v3"
GBIF_API_BASE = "https://api.gbif.org/v1"


def haversine_distance_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Computes great-circle distance between two points in kilometers."""
    r = 6371.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * r * asin(sqrt(max(0.0, min(1.0, a))))


class OBISBiodiversityService:
    """Client for official OBIS occurrence APIs."""

    def __init__(self, base_url: str = OBIS_API_BASE, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search_occurrences(
        self,
        scientific_name: Optional[str] = None,
        min_longitude: Optional[float] = None,
        min_latitude: Optional[float] = None,
        max_longitude: Optional[float] = None,
        max_latitude: Optional[float] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        size: int = 50,
    ) -> List[Dict[str, Any]]:
        """Queries live OBIS API and normalizes occurrences."""
        params: Dict[str, Any] = {"size": min(size, 500)}
        if scientific_name:
            params["scientificname"] = scientific_name

        # If spatial bounding box is specified, convert to WKT polygon for OBIS
        if all(v is not None for v in [min_longitude, min_latitude, max_longitude, max_latitude]):
            wkt = (
                f"POLYGON(({min_longitude} {min_latitude}, "
                f"{max_longitude} {min_latitude}, "
                f"{max_longitude} {max_latitude}, "
                f"{min_longitude} {max_latitude}, "
                f"{min_longitude} {min_latitude}))"
            )
            params["geometry"] = wkt

        if start_date:
            params["startdate"] = start_date[:10]
        if end_date:
            params["enddate"] = end_date[:10]

        url = f"{self.base_url}/occurrence"
        with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for raw in data.get("results", []):
            occ_id = str(raw.get("id") or raw.get("occurrenceID") or uuid.uuid4())
            lat = raw.get("decimalLatitude")
            lon = raw.get("decimalLongitude")
            if lat is None or lon is None:
                continue

            results.append({
                "provider": "obis",
                "occurrence_id": occ_id,
                "scientific_name": raw.get("scientificName") or scientific_name or "Unknown",
                "accepted_scientific_name": raw.get("aphiaID") and raw.get("species") or raw.get("scientificName"),
                "aphia_id": raw.get("aphiaID"),
                "taxon_rank": raw.get("taxonRank"),
                "kingdom": raw.get("kingdom"),
                "phylum": raw.get("phylum"),
                "class_name": raw.get("class"),
                "order_name": raw.get("order"),
                "family": raw.get("family"),
                "genus": raw.get("genus"),
                "latitude": float(lat),
                "longitude": float(lon),
                "coordinate_uncertainty_meters": raw.get("coordinateUncertaintyInMeters"),
                "depth_meters": raw.get("depth") or raw.get("minimumDepthInMeters"),
                "event_date": raw.get("eventDate"),
                "year": raw.get("date_year"),
                "basis_of_record": raw.get("basisOfRecord"),
                "institution_code": raw.get("institutionCode"),
                "dataset_name": raw.get("datasetName"),
                "licence": raw.get("license"),
                "bibliographic_citation": raw.get("bibliographicCitation"),
                "raw_record": raw,
            })
        return results


class GBIFBiodiversityService:
    """Client for official GBIF occurrence search APIs."""

    def __init__(self, base_url: str = GBIF_API_BASE, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search_occurrences(
        self,
        scientific_name: Optional[str] = None,
        min_longitude: Optional[float] = None,
        min_latitude: Optional[float] = None,
        max_longitude: Optional[float] = None,
        max_latitude: Optional[float] = None,
        year: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Queries live GBIF occurrence search API and normalizes occurrences."""
        params: Dict[str, Any] = {"limit": min(limit, 300)}
        if scientific_name:
            params["scientificName"] = scientific_name

        if all(v is not None for v in [min_longitude, min_latitude, max_longitude, max_latitude]):
            # GBIF decimalLatitude and decimalLongitude format: min,max
            params["decimalLatitude"] = f"{min_latitude},{max_latitude}"
            params["decimalLongitude"] = f"{min_longitude},{max_longitude}"

        if year:
            params["year"] = year

        # Focus on marine occurrences
        params["hasCoordinate"] = "true"

        url = f"{self.base_url}/occurrence/search"
        with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for raw in data.get("results", []):
            occ_id = str(raw.get("key") or raw.get("occurrenceID") or uuid.uuid4())
            lat = raw.get("decimalLatitude")
            lon = raw.get("decimalLongitude")
            if lat is None or lon is None:
                continue

            results.append({
                "provider": "gbif",
                "occurrence_id": occ_id,
                "scientific_name": raw.get("scientificName") or scientific_name or "Unknown",
                "accepted_scientific_name": raw.get("acceptedScientificName") or raw.get("scientificName"),
                "aphia_id": None,  # Can be populated via WoRMS reconciliation
                "taxon_rank": raw.get("taxonRank"),
                "kingdom": raw.get("kingdom"),
                "phylum": raw.get("phylum"),
                "class_name": raw.get("class"),
                "order_name": raw.get("order"),
                "family": raw.get("family"),
                "genus": raw.get("genus"),
                "latitude": float(lat),
                "longitude": float(lon),
                "coordinate_uncertainty_meters": raw.get("coordinateUncertaintyInMeters"),
                "depth_meters": raw.get("depth"),
                "event_date": raw.get("eventDate"),
                "year": raw.get("year"),
                "basis_of_record": raw.get("basisOfRecord"),
                "institution_code": raw.get("institutionCode"),
                "dataset_name": raw.get("datasetName"),
                "licence": raw.get("license"),
                "bibliographic_citation": raw.get("references"),
                "raw_record": raw,
            })
        return results


class BiodiversityReconciliationEngine:
    """
    Persists marine biodiversity occurrences in PostgreSQL/PostGIS and reconciles
    duplicate records across OBIS and GBIF without silently deleting original source data.
    """

    def persist_occurrences(self, db: Session, occurrences: List[Dict[str, Any]]) -> int:
        """Inserts occurrences into PostGIS with geometry point, avoiding duplicates."""
        inserted = 0
        for occ in occurrences:
            # Check existing by provider and occurrence_id
            existing = db.execute(
                select(MarineSpeciesOccurrenceModel).where(
                    and_(
                        MarineSpeciesOccurrenceModel.provider == occ["provider"],
                        MarineSpeciesOccurrenceModel.occurrence_id == occ["occurrence_id"],
                    )
                )
            ).scalar_one_or_none()

            if existing:
                continue

            lon = occ["longitude"]
            lat = occ["latitude"]
            wkt_geom = f"SRID=4326;POINT({lon} {lat})"

            record = MarineSpeciesOccurrenceModel(
                id=str(uuid.uuid4()),
                provider=occ["provider"],
                occurrence_id=occ["occurrence_id"],
                scientific_name=occ["scientific_name"][:256],
                accepted_scientific_name=occ.get("accepted_scientific_name") and occ["accepted_scientific_name"][:256],
                aphia_id=occ.get("aphia_id"),
                taxon_rank=occ.get("taxon_rank"),
                kingdom=occ.get("kingdom"),
                phylum=occ.get("phylum"),
                class_name=occ.get("class_name"),
                order_name=occ.get("order_name"),
                family=occ.get("family"),
                genus=occ.get("genus"),
                geom=wkt_geom,
                latitude=lat,
                longitude=lon,
                coordinate_uncertainty_meters=occ.get("coordinate_uncertainty_meters"),
                depth_meters=occ.get("depth_meters"),
                event_date=occ.get("event_date"),
                year=occ.get("year"),
                basis_of_record=occ.get("basis_of_record"),
                institution_code=occ.get("institution_code"),
                dataset_name=occ.get("dataset_name"),
                licence=occ.get("licence"),
                bibliographic_citation=occ.get("bibliographic_citation"),
                raw_record=occ.get("raw_record", {}),
                is_reconciled=False,
            )
            db.add(record)
            inserted += 1

        db.commit()
        return inserted

    def reconcile_duplicates(
        self,
        db: Session,
        distance_threshold_km: float = 5.0,
        scientific_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Identifies cross-provider duplicates between OBIS and GBIF.
        Records sharing matching genus/species, observation dates, and coordinates
        within the distance threshold are assigned a unified reconciled_cluster_id.
        """
        query = select(MarineSpeciesOccurrenceModel)
        if scientific_name:
            query = query.where(MarineSpeciesOccurrenceModel.scientific_name.ilike(f"%{scientific_name}%"))

        records = db.execute(query).scalars().all()
        obis_records = [r for r in records if r.provider == "obis"]
        gbif_records = [r for r in records if r.provider == "gbif"]

        clusters_created = 0
        reconciled_count = 0

        for o in obis_records:
            for g in gbif_records:
                # Name matching (genus or species)
                o_name = o.scientific_name.lower().split()[0] if o.scientific_name else ""
                g_name = g.scientific_name.lower().split()[0] if g.scientific_name else ""
                if not o_name or o_name != g_name:
                    continue

                # Date matching (same year/event date)
                if o.year and g.year and o.year != g.year:
                    continue

                # Distance calculation
                dist = haversine_distance_km(o.longitude, o.latitude, g.longitude, g.latitude)
                if dist <= distance_threshold_km:
                    cluster_id = o.reconciled_cluster_id or g.reconciled_cluster_id or f"clust-{uuid.uuid4().hex[:12]}"
                    if not o.is_reconciled or o.reconciled_cluster_id != cluster_id:
                        o.is_reconciled = True
                        o.reconciled_cluster_id = cluster_id
                        reconciled_count += 1
                    if not g.is_reconciled or g.reconciled_cluster_id != cluster_id:
                        g.is_reconciled = True
                        g.reconciled_cluster_id = cluster_id
                        reconciled_count += 1
                    clusters_created += 1

        db.commit()
        return {
            "total_records_evaluated": len(records),
            "clusters_identified": clusters_created,
            "records_reconciled": reconciled_count,
            "distance_threshold_km": distance_threshold_km,
        }

    def search_persisted_occurrences(
        self,
        db: Session,
        scientific_name: Optional[str] = None,
        min_longitude: Optional[float] = None,
        min_latitude: Optional[float] = None,
        max_longitude: Optional[float] = None,
        max_latitude: Optional[float] = None,
        provider: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MarineSpeciesOccurrenceModel]:
        """Queries stored occurrences with spatial BBOX and attribute filters."""
        conditions = []
        if scientific_name:
            conditions.append(MarineSpeciesOccurrenceModel.scientific_name.ilike(f"%{scientific_name}%"))
        if provider:
            conditions.append(MarineSpeciesOccurrenceModel.provider == provider.lower())
        if year:
            conditions.append(MarineSpeciesOccurrenceModel.year == year)

        if all(v is not None for v in [min_longitude, min_latitude, max_longitude, max_latitude]):
            conditions.append(
                and_(
                    MarineSpeciesOccurrenceModel.longitude >= min_longitude,
                    MarineSpeciesOccurrenceModel.longitude <= max_longitude,
                    MarineSpeciesOccurrenceModel.latitude >= min_latitude,
                    MarineSpeciesOccurrenceModel.latitude <= max_latitude,
                )
            )

        query = select(MarineSpeciesOccurrenceModel)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(MarineSpeciesOccurrenceModel.created_at.desc()).offset(offset).limit(limit)

        return list(db.execute(query).scalars().all())


obis_service = OBISBiodiversityService()
gbif_service = GBIFBiodiversityService()
reconciliation_engine = BiodiversityReconciliationEngine()
