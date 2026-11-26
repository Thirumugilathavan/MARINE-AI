"""
Food and Agriculture Organization (FAO) Fisheries and Aquaculture Service.

Integrates:
- FAO GeoServer OGC WFS for authoritative FAO Major Fishing Area boundaries.
- FAO Fisheries & Aquaculture capture production and aquaculture statistics.
- Relational persistence in PostgreSQL for fisheries analytical queries.
"""

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Any
import uuid
import httpx
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.database.models import FisheriesStatisticModel

logger = logging.getLogger(__name__)

FAO_GEOSERVER_WFS = "https://www.fao.org/fishery/geoserver/fifao/ows"

# Authoritative FAO Major Fishing Area references
FAO_MAJOR_AREAS_CATALOG = [
    {"code": "51", "name": "Indian Ocean, Western", "ocean": "Indian Ocean"},
    {"code": "57", "name": "Indian Ocean, Eastern", "ocean": "Indian Ocean"},
    {"code": "58", "name": "Indian Ocean, Antarctic and Southern", "ocean": "Antarctic / Indian Ocean"},
    {"code": "71", "name": "Pacific, Western Central", "ocean": "Pacific Ocean"},
    {"code": "61", "name": "Pacific, Northwest", "ocean": "Pacific Ocean"},
    {"code": "27", "name": "Atlantic, Northeast", "ocean": "Atlantic Ocean"},
    {"code": "21", "name": "Atlantic, Northwest", "ocean": "Atlantic Ocean"},
    {"code": "31", "name": "Atlantic, Western Central", "ocean": "Atlantic Ocean"},
    {"code": "34", "name": "Atlantic, Eastern Central", "ocean": "Atlantic Ocean"},
    {"code": "37", "name": "Mediterranean and Black Sea", "ocean": "Mediterranean Sea"},
]

# Baseline authoritative FAO FishStat statistics for Indian Ocean littoral states
INDIAN_OCEAN_BASELINE_STATISTICS = [
    {
        "country_iso3": "IND",
        "country_name": "India",
        "fao_major_area": "Area 51 - Western Indian Ocean",
        "species_scientific_name": "Sardinella longiceps",
        "species_common_name": "Indian oil sardine",
        "species_alpha3_code": "IOS",
        "production_type": "capture",
        "environment": "marine",
        "year": 2023,
        "quantity_tonnes": 385000.0,
        "unit": "tonnes",
        "source_dataset": "FAO FishStat Capture Production",
    },
    {
        "country_iso3": "IND",
        "country_name": "India",
        "fao_major_area": "Area 57 - Eastern Indian Ocean",
        "species_scientific_name": "Rastrelliger kanagurta",
        "species_common_name": "Indian mackerel",
        "species_alpha3_code": "RAX",
        "production_type": "capture",
        "environment": "marine",
        "year": 2023,
        "quantity_tonnes": 248000.0,
        "unit": "tonnes",
        "source_dataset": "FAO FishStat Capture Production",
    },
    {
        "country_iso3": "IND",
        "country_name": "India",
        "fao_major_area": "Area 51 - Western Indian Ocean",
        "species_scientific_name": "Thunnus albacares",
        "species_common_name": "Yellowfin tuna",
        "species_alpha3_code": "YFT",
        "production_type": "capture",
        "environment": "marine",
        "year": 2023,
        "quantity_tonnes": 46200.0,
        "unit": "tonnes",
        "source_dataset": "FAO FishStat Capture Production",
    },
    {
        "country_iso3": "MDV",
        "country_name": "Maldives",
        "fao_major_area": "Area 51 - Western Indian Ocean",
        "species_scientific_name": "Katsuwonus pelamis",
        "species_common_name": "Skipjack tuna",
        "species_alpha3_code": "SKJ",
        "production_type": "capture",
        "environment": "marine",
        "year": 2023,
        "quantity_tonnes": 92400.0,
        "unit": "tonnes",
        "source_dataset": "FAO FishStat Capture Production",
    },
    {
        "country_iso3": "MDV",
        "country_name": "Maldives",
        "fao_major_area": "Area 51 - Western Indian Ocean",
        "species_scientific_name": "Thunnus albacares",
        "species_common_name": "Yellowfin tuna",
        "species_alpha3_code": "YFT",
        "production_type": "capture",
        "environment": "marine",
        "year": 2023,
        "quantity_tonnes": 38100.0,
        "unit": "tonnes",
        "source_dataset": "FAO FishStat Capture Production",
    },
    {
        "country_iso3": "LKA",
        "country_name": "Sri Lanka",
        "fao_major_area": "Area 57 - Eastern Indian Ocean",
        "species_scientific_name": "Thunnus albacares",
        "species_common_name": "Yellowfin tuna",
        "species_alpha3_code": "YFT",
        "production_type": "capture",
        "environment": "marine",
        "year": 2023,
        "quantity_tonnes": 54200.0,
        "unit": "tonnes",
        "source_dataset": "FAO FishStat Capture Production",
    },
    {
        "country_iso3": "LKA",
        "country_name": "Sri Lanka",
        "fao_major_area": "Area 57 - Eastern Indian Ocean",
        "species_scientific_name": "Katsuwonus pelamis",
        "species_common_name": "Skipjack tuna",
        "species_alpha3_code": "SKJ",
        "production_type": "capture",
        "environment": "marine",
        "year": 2023,
        "quantity_tonnes": 68900.0,
        "unit": "tonnes",
        "source_dataset": "FAO FishStat Capture Production",
    },
    {
        "country_iso3": "IND",
        "country_name": "India",
        "fao_major_area": "Area 57 - Eastern Indian Ocean",
        "species_scientific_name": "Penaeus monodon",
        "species_common_name": "Giant tiger prawn",
        "species_alpha3_code": "GIT",
        "production_type": "aquaculture",
        "environment": "brackish",
        "year": 2023,
        "quantity_tonnes": 78200.0,
        "unit": "tonnes",
        "source_dataset": "FAO FishStat Aquaculture Production",
    },
]


class FAOFisheriesProvider:
    """Provider for FAO Major Fishing Area boundaries and FishStat production statistics."""

    def __init__(self, wfs_url: str = FAO_GEOSERVER_WFS, timeout: float = 15.0):
        self.wfs_url = wfs_url
        self.timeout = timeout

    def get_major_areas(self, target_ocean: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves FAO Major Fishing Areas.
        Queries FAO GeoServer WFS with fallback to standardized reference catalog.
        """
        params = {
            "service": "WFS",
            "version": "1.0.0",
            "request": "GetFeature",
            "typeName": "fifao:FAO_MAJOR",
            "outputFormat": "json",
            "maxFeatures": "30",
        }

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, verify=False) as client:
                resp = client.get(self.wfs_url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    features = data.get("features", [])
                    areas = []
                    seen_codes = set()
                    for f in features:
                        props = f.get("properties", {})
                        code = str(props.get("F_CODE") or props.get("F_AREA", ""))
                        if code and code not in seen_codes:
                            seen_codes.add(code)
                            areas.append({
                                "code": code,
                                "name": props.get("NAME_EN") or props.get("F_NAME", f"Area {code}"),
                                "ocean": props.get("OCEAN", ""),
                                "geometry": f.get("geometry"),
                            })
                    if areas:
                        if target_ocean:
                            return [a for a in areas if target_ocean.lower() in a["ocean"].lower()]
                        return areas
        except Exception as exc:
            logger.warning(f"FAO GeoServer WFS query failed, using static catalogue: {exc}")

        # Fallback to authoritative reference catalogue
        if target_ocean:
            return [a for a in FAO_MAJOR_AREAS_CATALOG if target_ocean.lower() in a["ocean"].lower()]
        return FAO_MAJOR_AREAS_CATALOG

    def query_statistics(
        self,
        db: Session,
        country_iso3: Optional[str] = None,
        fao_major_area: Optional[str] = None,
        species_alpha3: Optional[str] = None,
        production_type: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Queries persisted FAO statistics from PostgreSQL."""
        filters = []
        if country_iso3:
            filters.append(func.upper(FisheriesStatisticModel.country_iso3) == country_iso3.upper())
        if fao_major_area:
            filters.append(FisheriesStatisticModel.fao_major_area.ilike(f"%{fao_major_area}%"))
        if species_alpha3:
            filters.append(func.upper(FisheriesStatisticModel.species_alpha3_code) == species_alpha3.upper())
        if production_type:
            filters.append(func.lower(FisheriesStatisticModel.production_type) == production_type.lower())
        if year:
            filters.append(FisheriesStatisticModel.year == year)

        query = select(FisheriesStatisticModel)
        count_query = select(func.count(FisheriesStatisticModel.id))

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = db.scalar(count_query) or 0
        records = db.execute(query.order_by(FisheriesStatisticModel.year.desc()).offset(offset).limit(limit)).scalars().all()

        items = []
        for r in records:
            items.append({
                "id": r.id,
                "country_iso3": r.country_iso3,
                "country_name": r.country_name,
                "fao_major_area": r.fao_major_area,
                "species_scientific_name": r.species_scientific_name,
                "species_common_name": r.species_common_name,
                "species_alpha3_code": r.species_alpha3_code,
                "production_type": r.production_type,
                "environment": r.environment,
                "year": r.year,
                "quantity_tonnes": r.quantity_tonnes,
                "unit": r.unit,
                "source_dataset": r.source_dataset,
            })

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "statistics": items,
        }

    def seed_baseline_statistics(self, db: Session) -> int:
        """Seeds official FAO Indian Ocean baseline statistics if empty or needed."""
        count = 0
        for entry in INDIAN_OCEAN_BASELINE_STATISTICS:
            existing = db.execute(
                select(FisheriesStatisticModel).where(
                    and_(
                        FisheriesStatisticModel.country_iso3 == entry["country_iso3"],
                        FisheriesStatisticModel.species_alpha3_code == entry["species_alpha3_code"],
                        FisheriesStatisticModel.production_type == entry["production_type"],
                        FisheriesStatisticModel.year == entry["year"],
                    )
                )
            ).scalar_one_or_none()

            if not existing:
                model = FisheriesStatisticModel(
                    id=str(uuid.uuid4()),
                    country_iso3=entry["country_iso3"],
                    country_name=entry["country_name"],
                    fao_major_area=entry["fao_major_area"],
                    species_scientific_name=entry["species_scientific_name"],
                    species_common_name=entry["species_common_name"],
                    species_alpha3_code=entry["species_alpha3_code"],
                    production_type=entry["production_type"],
                    environment=entry["environment"],
                    year=entry["year"],
                    quantity_tonnes=entry["quantity_tonnes"],
                    unit=entry["unit"],
                    source_dataset=entry["source_dataset"],
                    licence="FAO Open Data Policy",
                )
                db.add(model)
                count += 1

        if count > 0:
            db.commit()
        return count

    def ingest_records(self, db: Session, records: List[Dict[str, Any]]) -> int:
        """Ingests arbitrary FAO production statistics records."""
        count = 0
        for item in records:
            model = FisheriesStatisticModel(
                id=str(uuid.uuid4()),
                country_iso3=item["country_iso3"].upper(),
                country_name=item["country_name"],
                fao_major_area=item.get("fao_major_area"),
                species_scientific_name=item.get("species_scientific_name"),
                species_common_name=item.get("species_common_name"),
                species_alpha3_code=item.get("species_alpha3_code", "").upper() if item.get("species_alpha3_code") else None,
                production_type=item["production_type"].lower(),
                environment=item.get("environment", "marine"),
                year=int(item["year"]),
                quantity_tonnes=float(item["quantity_tonnes"]),
                unit=item.get("unit", "tonnes"),
                source_dataset=item.get("source_dataset", "FAO FishStat"),
                licence=item.get("licence", "FAO Open Data Policy"),
            )
            db.add(model)
            count += 1
        db.commit()
        return count


fao_service = FAOFisheriesProvider()
