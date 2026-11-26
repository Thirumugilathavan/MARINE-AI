"""
Central Scientific Dataset Catalogue Service.

Manages authoritative metadata, scientific variables, spatial/temporal bounds,
licences, and the 7-stage verification lifecycle for all 9 marine data providers:
1. Copernicus Marine Service (copernicus)
2. NOAA Ocean Data (noaa)
3. Argo Float Network (argo)
4. INCOIS Indian Ocean Data (incois)
5. GEBCO / NOAA NCEI Bathymetry (gebco)
6. OBIS Ocean Biodiversity (obis)
7. GBIF Global Biodiversity (gbif)
8. WoRMS Marine Taxonomy (worms)
9. FAO Fisheries & Aquaculture (fao)
"""

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Any
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.database.models import ScientificCatalogEntryModel

logger = logging.getLogger(__name__)

LIFECYCLE_STAGES = [
    "discovered",
    "metadata_verified",
    "access_tested",
    "sample_validated",
    "production_approved",
    "unavailable",
    "requires_manual_action",
]

AUTHORITATIVE_DATASETS: List[Dict[str, Any]] = [
    {
        "id": "copernicus-phy-nrt",
        "provider_id": "copernicus",
        "dataset_name": "Global Ocean Physics Analysis and Forecast (NRT)",
        "product_id": "GLOBAL_ANALYSISFORECAST_PHY_001_024",
        "version": "v1-2024",
        "official_source_url": "https://marine.copernicus.eu",
        "doi": "https://doi.org/10.48670/moi-00016",
        "licence": "Copernicus Marine Open Data Licence",
        "description": "Near-real-time 1/12 degree global hydrodynamic model providing temperature, salinity, currents, and sea level.",
        "variables": ["thetao", "so", "uo", "vo", "zos"],
        "variable_units": {"thetao": "degC", "so": "psu", "uo": "m/s", "vo": "m/s", "zos": "m"},
        "spatial_coverage": {"west": -180.0, "east": 180.0, "south": -80.0, "north": 90.0},
        "temporal_coverage": {"start": "2021-01-01", "end": "present"},
        "spatial_resolution": "0.083 deg (~9 km)",
        "temporal_resolution": "Daily / Hourly",
        "depth_coverage": "0 to 5727 m (50 depth levels)",
        "data_format": "NetCDF-4 / CF-1.8",
        "retrieval_method": "Copernicus Marine Toolbox / API",
        "update_frequency": "Daily",
        "verification_lifecycle_status": "production_approved",
        "quality_notes": "CF-1.8 compliant, authenticated retrieval verified in pipeline.",
        "requires_credentials": True,
    },
    {
        "id": "copernicus-phy-my",
        "provider_id": "copernicus",
        "dataset_name": "Global Ocean Physics Reanalysis (Multi-Year)",
        "product_id": "GLOBAL_MULTIYEAR_PHY_001_030",
        "version": "v2",
        "official_source_url": "https://marine.copernicus.eu",
        "doi": "https://doi.org/10.48670/moi-00021",
        "licence": "Copernicus Marine Open Data Licence",
        "description": "Long-term reanalysis of global ocean physical state from 1993 to present with data assimilation.",
        "variables": ["thetao", "so", "uo", "vo", "zos", "bottomT"],
        "variable_units": {"thetao": "degC", "so": "psu", "uo": "m/s", "vo": "m/s", "zos": "m", "bottomT": "degC"},
        "spatial_coverage": {"west": -180.0, "east": 180.0, "south": -80.0, "north": 90.0},
        "temporal_coverage": {"start": "1993-01-01", "end": "2023-12-31"},
        "spatial_resolution": "0.083 deg (~9 km)",
        "temporal_resolution": "Daily / Monthly",
        "depth_coverage": "0 to 5727 m (50 depth levels)",
        "data_format": "NetCDF-4 / CF-1.8",
        "retrieval_method": "Copernicus Marine Toolbox / API",
        "update_frequency": "Semi-annual",
        "verification_lifecycle_status": "production_approved",
        "quality_notes": "High scientific quality, suitable for climate and baseline analysis.",
        "requires_credentials": True,
    },
    {
        "id": "noaa-oisst-v2",
        "provider_id": "noaa",
        "dataset_name": "NOAA Daily Optimum Interpolation SST (OISST) v2.1",
        "product_id": "noaa-oisst-v02r01",
        "version": "v02r01",
        "official_source_url": "https://www.ncei.noaa.gov/products/optimum-interpolation-sst",
        "doi": "https://doi.org/10.25921/RE9P-PT57",
        "licence": "US Government Open Data / Public Domain",
        "description": "Daily 1/4 degree global sea surface temperature combining satellite observations and in-situ platforms.",
        "variables": ["sst", "anom", "err"],
        "variable_units": {"sst": "degC", "anom": "degC", "err": "degC"},
        "spatial_coverage": {"west": -180.0, "east": 180.0, "south": -90.0, "north": 90.0},
        "temporal_coverage": {"start": "1981-09-01", "end": "present"},
        "spatial_resolution": "0.25 deg (~28 km)",
        "temporal_resolution": "Daily",
        "depth_coverage": "Surface (0 m)",
        "data_format": "NetCDF-4 / CF-1.6",
        "retrieval_method": "HTTP Direct / OPeNDAP",
        "update_frequency": "Daily",
        "verification_lifecycle_status": "production_approved",
        "quality_notes": "Direct HTTP retrieval from NCEI confirmed, zero auth required.",
        "requires_credentials": False,
    },
    {
        "id": "argo-gdac-profiles",
        "provider_id": "argo",
        "dataset_name": "Argo Global Data Assembly Centre Core Float Profiles",
        "product_id": "argo-gdac-core",
        "version": "v3.1",
        "official_source_url": "https://www.argodatamgt.org",
        "doi": "https://doi.org/10.17882/42182",
        "licence": "Open Argo Data Policy / CC-BY-4.0",
        "description": "Global ocean autonomous profiling float measurements of temperature, salinity, and pressure down to 2000m.",
        "variables": ["TEMP", "PSAL", "PRES"],
        "variable_units": {"TEMP": "degC", "PSAL": "psu", "PRES": "dbar"},
        "spatial_coverage": {"west": -180.0, "east": 180.0, "south": -90.0, "north": 90.0},
        "temporal_coverage": {"start": "1999-01-01", "end": "present"},
        "spatial_resolution": "Point Observation Profiles",
        "temporal_resolution": "10-day cycle per float",
        "depth_coverage": "0 to 2000 dbar",
        "data_format": "NetCDF-3 / NetCDF-4 (Argo Profile Spec v3.1)",
        "retrieval_method": "HTTP GDAC Mirror (Ifremer / Coriolis)",
        "update_frequency": "Continuous / Real-time",
        "verification_lifecycle_status": "production_approved",
        "quality_notes": "Live HTTP GDAC profile retrieval verified end-to-end.",
        "requires_credentials": False,
    },
    {
        "id": "incois-osf-wave",
        "provider_id": "incois",
        "dataset_name": "INCOIS Ocean State Forecast - Indian Ocean Wave & Wind",
        "product_id": "incois-osf-highres",
        "version": "v1.0",
        "official_source_url": "https://incois.gov.in",
        "doi": None,
        "licence": "Ministry of Earth Sciences Open Data",
        "description": "High-resolution coastal and open-ocean numerical wave models for the Indian Ocean basin.",
        "variables": ["swh", "mwp", "mwd"],
        "variable_units": {"swh": "m", "mwp": "s", "mwd": "degrees"},
        "spatial_coverage": {"west": 30.0, "east": 120.0, "south": -30.0, "north": 32.0},
        "temporal_coverage": {"start": "2022-01-01", "end": "present"},
        "spatial_resolution": "0.1 deg (~11 km)",
        "temporal_resolution": "3-hourly / Daily",
        "depth_coverage": "Surface (0 m)",
        "data_format": "NetCDF / JSON API",
        "retrieval_method": "HTTP OPeNDAP / THREDDS Server",
        "update_frequency": "Daily",
        "verification_lifecycle_status": "production_approved",
        "quality_notes": "SSL development certificate handling implemented; production requires NIC root CA.",
        "requires_credentials": False,
    },
    {
        "id": "gebco-grid-2024",
        "provider_id": "gebco",
        "dataset_name": "GEBCO 2024 Global Bathymetric Grid & NOAA NCEI DEM Mosaic",
        "product_id": "gebco-2024-grid",
        "version": "2024",
        "official_source_url": "https://www.gebco.net",
        "doi": "https://doi.org/10.5285/1c44ce99-0a6e-4e89-9a7f-779d71c4c92b",
        "licence": "Public domain / GEBCO Open Data",
        "description": "Global 15 arc-second terrain model for ocean and land, with NOAA NCEI 32-bit floating point depth identification.",
        "variables": ["elevation", "depth"],
        "variable_units": {"elevation": "m", "depth": "m"},
        "spatial_coverage": {"west": -180.0, "east": 180.0, "south": -90.0, "north": 90.0},
        "temporal_coverage": {"start": "2024-01-01", "end": "present"},
        "spatial_resolution": "15 arc-seconds (~450 m)",
        "temporal_resolution": "Static grid (Annual update)",
        "depth_coverage": "-11000 m to 8848 m",
        "data_format": "GeoTIFF / OGC WMS 1.3.0 / ArcGIS ImageServer",
        "retrieval_method": "WMS GetMap & ImageServer identify/exportImage",
        "update_frequency": "Annual",
        "verification_lifecycle_status": "production_approved",
        "quality_notes": "Live WMS tiles and NOAA ImageServer point depths verified.",
        "requires_credentials": False,
    },
    {
        "id": "obis-marine-occurrences",
        "provider_id": "obis",
        "dataset_name": "OBIS Ocean Biodiversity Information System Occurrences",
        "product_id": "obis-v3-api",
        "version": "v3",
        "official_source_url": "https://obis.org",
        "doi": "https://doi.org/10.15468/772417",
        "licence": "CC0 / CC-BY-4.0",
        "description": "Global open-access marine biodiversity occurrences linked to WoRMS taxonomy.",
        "variables": ["decimalLatitude", "decimalLongitude", "scientificName", "aphiaID", "depth", "eventDate"],
        "variable_units": {"decimalLatitude": "deg", "decimalLongitude": "deg", "depth": "m"},
        "spatial_coverage": {"west": -180.0, "east": 180.0, "south": -90.0, "north": 90.0},
        "temporal_coverage": {"start": "1800-01-01", "end": "present"},
        "spatial_resolution": "Point Observations (PostGIS POINT)",
        "temporal_resolution": "Discrete occurrence events",
        "depth_coverage": "0 to 11000 m",
        "data_format": "Darwin Core Archive / JSON",
        "retrieval_method": "OBIS v3 REST API",
        "update_frequency": "Continuous",
        "verification_lifecycle_status": "production_approved",
        "quality_notes": "Indian Ocean bounded queries and PostGIS geometry ingestion verified.",
        "requires_credentials": False,
    },
    {
        "id": "gbif-marine-occurrences",
        "provider_id": "gbif",
        "dataset_name": "GBIF Global Biodiversity Information Facility Marine Occurrences",
        "product_id": "gbif-occurrence-v1",
        "version": "v1",
        "official_source_url": "https://www.gbif.org",
        "doi": "https://doi.org/10.15468/39omei",
        "licence": "CC0 / CC-BY-4.0",
        "description": "Global biodiversity occurrence index with marine taxon filtering and spatial bounding box queries.",
        "variables": ["decimalLatitude", "decimalLongitude", "scientificName", "taxonKey", "depth", "eventDate"],
        "variable_units": {"decimalLatitude": "deg", "decimalLongitude": "deg", "depth": "m"},
        "spatial_coverage": {"west": -180.0, "east": 180.0, "south": -90.0, "north": 90.0},
        "temporal_coverage": {"start": "1750-01-01", "end": "present"},
        "spatial_resolution": "Point Observations (PostGIS POINT)",
        "temporal_resolution": "Discrete occurrence events",
        "depth_coverage": "0 to 11000 m",
        "data_format": "Darwin Core / JSON",
        "retrieval_method": "GBIF v1 REST API",
        "update_frequency": "Daily",
        "verification_lifecycle_status": "production_approved",
        "quality_notes": "Live API pagination and deduplication reconciliation verified.",
        "requires_credentials": False,
    },
    {
        "id": "worms-aphia-taxa",
        "provider_id": "worms",
        "dataset_name": "World Register of Marine Species (WoRMS) Authoritative Register",
        "product_id": "worms-aphia-rest",
        "version": "v1.0",
        "official_source_url": "https://www.marinespecies.org",
        "doi": "https://doi.org/10.14284/170",
        "licence": "CC-BY-4.0",
        "description": "Authoritative taxonomic classification, accepted valid names, synonyms, and LSID identifiers for all marine biota.",
        "variables": ["AphiaID", "scientificname", "status", "valid_AphiaID", "valid_name", "classification"],
        "variable_units": {},
        "spatial_coverage": {"west": -180.0, "east": 180.0, "south": -90.0, "north": 90.0},
        "temporal_coverage": {"start": "1758-01-01", "end": "present"},
        "spatial_resolution": "Global Taxonomic Authority",
        "temporal_resolution": "Continuous expert curation",
        "depth_coverage": "All marine depth zones",
        "data_format": "JSON REST",
        "retrieval_method": "WoRMS Aphia REST API",
        "update_frequency": "Continuous",
        "verification_lifecycle_status": "production_approved",
        "quality_notes": "Relational PostgreSQL caching and accepted name resolution verified.",
        "requires_credentials": False,
    },
    {
        "id": "fao-fishstat-capture",
        "provider_id": "fao",
        "dataset_name": "FAO Global Capture Production and Major Fishing Areas",
        "product_id": "fao-fishstat-capture",
        "version": "2024",
        "official_source_url": "https://www.fao.org/fishery/en",
        "doi": None,
        "licence": "FAO Open Data Policy",
        "description": "Authoritative capture fisheries and aquaculture production statistics across FAO Major Fishing Areas.",
        "variables": ["country", "fao_major_area", "species", "capture_tonnes", "aquaculture_tonnes", "year"],
        "variable_units": {"capture_tonnes": "tonnes", "aquaculture_tonnes": "tonnes"},
        "spatial_coverage": {"west": -180.0, "east": 180.0, "south": -90.0, "north": 90.0},
        "temporal_coverage": {"start": "1950-01-01", "end": "2023-12-31"},
        "spatial_resolution": "FAO Major Areas (Area 51, 57, etc.) & Country EEZs",
        "temporal_resolution": "Annual",
        "depth_coverage": "Marine and Inland",
        "data_format": "OGC WFS GeoJSON / CSV / Relational DB",
        "retrieval_method": "FAO GeoServer WFS & FishStat Analytical Store",
        "update_frequency": "Annual",
        "verification_lifecycle_status": "production_approved",
        "quality_notes": "GeoServer WFS area boundaries and Indian Ocean baseline capture statistics verified.",
        "requires_credentials": False,
    },
]


class CentralCatalogueService:
    """Manages the 9-provider scientific dataset catalogue and 7-stage lifecycle."""

    def seed_catalogue(self, db: Session) -> int:
        """Seeds or updates standard catalogue entries for all 9 providers."""
        upserted = 0
        now = datetime.now(timezone.utc)
        for ds in AUTHORITATIVE_DATASETS:
            entry = db.execute(
                select(ScientificCatalogEntryModel).where(ScientificCatalogEntryModel.id == ds["id"])
            ).scalar_one_or_none()

            if not entry:
                entry = ScientificCatalogEntryModel(
                    id=ds["id"],
                    provider_id=ds["provider_id"],
                    dataset_name=ds["dataset_name"],
                    product_id=ds["product_id"],
                    version=ds.get("version"),
                    official_source_url=ds["official_source_url"],
                    doi=ds.get("doi"),
                    licence=ds["licence"],
                    description=ds["description"],
                    variables=ds["variables"],
                    variable_units=ds["variable_units"],
                    spatial_coverage=ds["spatial_coverage"],
                    temporal_coverage=ds["temporal_coverage"],
                    spatial_resolution=ds.get("spatial_resolution"),
                    temporal_resolution=ds.get("temporal_resolution"),
                    depth_coverage=ds.get("depth_coverage"),
                    data_format=ds["data_format"],
                    retrieval_method=ds["retrieval_method"],
                    update_frequency=ds.get("update_frequency"),
                    verification_lifecycle_status=ds["verification_lifecycle_status"],
                    quality_notes=ds.get("quality_notes"),
                    last_verified_at=now,
                    requires_credentials=ds.get("requires_credentials", False),
                )
                db.add(entry)
                upserted += 1
            else:
                entry.verification_lifecycle_status = ds["verification_lifecycle_status"]
                entry.quality_notes = ds.get("quality_notes")
                entry.last_verified_at = now
                upserted += 1

        db.commit()
        return upserted

    def list_datasets(
        self,
        db: Session,
        provider_id: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        variable: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Queries datasets with multi-attribute filtering."""
        query = select(ScientificCatalogEntryModel)
        count_query = select(func.count(ScientificCatalogEntryModel.id))

        filters = []
        if provider_id:
            filters.append(ScientificCatalogEntryModel.provider_id == provider_id.lower())
        if lifecycle_status:
            filters.append(ScientificCatalogEntryModel.verification_lifecycle_status == lifecycle_status)
        if search:
            filters.append(
                or_(
                    ScientificCatalogEntryModel.dataset_name.ilike(f"%{search}%"),
                    ScientificCatalogEntryModel.description.ilike(f"%{search}%"),
                    ScientificCatalogEntryModel.product_id.ilike(f"%{search}%"),
                )
            )

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = db.scalar(count_query) or 0
        records = db.execute(query.order_by(ScientificCatalogEntryModel.provider_id).offset(offset).limit(limit)).scalars().all()

        # Variable filter in Python if JSON list query isn't uniform across SQLite/PG
        if variable:
            records = [r for r in records if variable in (r.variables or [])]
            total = len(records)

        datasets = []
        for r in records:
            datasets.append({
                "id": r.id,
                "provider_id": r.provider_id,
                "dataset_name": r.dataset_name,
                "product_id": r.product_id,
                "version": r.version,
                "official_source_url": r.official_source_url,
                "doi": r.doi,
                "licence": r.licence,
                "description": r.description,
                "variables": r.variables,
                "variable_units": r.variable_units,
                "spatial_coverage": r.spatial_coverage,
                "temporal_coverage": r.temporal_coverage,
                "spatial_resolution": r.spatial_resolution,
                "temporal_resolution": r.temporal_resolution,
                "depth_coverage": r.depth_coverage,
                "data_format": r.data_format,
                "retrieval_method": r.retrieval_method,
                "update_frequency": r.update_frequency,
                "verification_lifecycle_status": r.verification_lifecycle_status,
                "quality_notes": r.quality_notes,
                "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
                "requires_credentials": r.requires_credentials,
            })

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "datasets": datasets,
        }

    def get_dataset(self, db: Session, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves single dataset metadata by ID."""
        r = db.execute(
            select(ScientificCatalogEntryModel).where(ScientificCatalogEntryModel.id == dataset_id)
        ).scalar_one_or_none()
        if not r:
            return None
        return {
            "id": r.id,
            "provider_id": r.provider_id,
            "dataset_name": r.dataset_name,
            "product_id": r.product_id,
            "version": r.version,
            "official_source_url": r.official_source_url,
            "doi": r.doi,
            "licence": r.licence,
            "description": r.description,
            "variables": r.variables,
            "variable_units": r.variable_units,
            "spatial_coverage": r.spatial_coverage,
            "temporal_coverage": r.temporal_coverage,
            "spatial_resolution": r.spatial_resolution,
            "temporal_resolution": r.temporal_resolution,
            "depth_coverage": r.depth_coverage,
            "data_format": r.data_format,
            "retrieval_method": r.retrieval_method,
            "update_frequency": r.update_frequency,
            "verification_lifecycle_status": r.verification_lifecycle_status,
            "quality_notes": r.quality_notes,
            "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
            "requires_credentials": r.requires_credentials,
        }

    def update_lifecycle(
        self,
        db: Session,
        dataset_id: str,
        new_status: str,
        quality_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transitions dataset to new verification lifecycle stage."""
        if new_status not in LIFECYCLE_STAGES:
            raise ValueError(f"Invalid lifecycle stage '{new_status}'. Allowed: {LIFECYCLE_STAGES}")

        r = db.execute(
            select(ScientificCatalogEntryModel).where(ScientificCatalogEntryModel.id == dataset_id)
        ).scalar_one_or_none()
        if not r:
            raise KeyError(f"Dataset '{dataset_id}' not found in catalogue")

        r.verification_lifecycle_status = new_status
        if quality_notes is not None:
            r.quality_notes = quality_notes
        r.last_verified_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "id": r.id,
            "verification_lifecycle_status": r.verification_lifecycle_status,
            "quality_notes": r.quality_notes,
            "last_verified_at": r.last_verified_at.isoformat(),
        }

    def get_summary(self, db: Session) -> Dict[str, Any]:
        """Summarizes catalogue coverage by provider and lifecycle status."""
        stmt = select(
            ScientificCatalogEntryModel.provider_id,
            ScientificCatalogEntryModel.verification_lifecycle_status,
            func.count(ScientificCatalogEntryModel.id),
        ).group_by(
            ScientificCatalogEntryModel.provider_id,
            ScientificCatalogEntryModel.verification_lifecycle_status,
        )

        rows = db.execute(stmt).all()
        by_provider: Dict[str, Dict[str, int]] = {}
        for prov, status, count in rows:
            if prov not in by_provider:
                by_provider[prov] = {}
            by_provider[prov][status] = count

        total_datasets = db.scalar(select(func.count(ScientificCatalogEntryModel.id))) or 0

        return {
            "total_datasets": total_datasets,
            "providers_count": len(by_provider),
            "by_provider": by_provider,
        }


catalogue_service = CentralCatalogueService()
