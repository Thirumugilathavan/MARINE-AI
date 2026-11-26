# SSTRIX MARINE-AI / SIH25041 — Missing Data Acquisition Plan

**Plan Date**: November 26, 2026  
**Architect**: Lead Oceanographic Data Platform Architect  
**Repository**: `https://github.com/Thirumugilathavan/MARINE-AI.git`  
**Active Branch**: `feature/marine-complete-backend-platform`  
**Baseline Git Commit**: `3b057d7`  

---

## 1. Objective and Operating Principles

This acquisition plan specifies the engineering execution strategy to acquire **ONLY** genuinely missing marine scientific data without duplicating, recreating, or overwriting existing integrations.

### Guiding Principles
1. **Zero Duplication**: Preserve all existing Copernicus, NOAA SST, Argo, INCOIS wind, GEBCO bathymetry, OBIS/GBIF occurrences, and FAO statistics.
2. **Reuse Existing Architecture**: Leverage existing Pydantic schemas, SQLAlchemy models, SeaweedFS S3 client, and the unified ingestion orchestrator.
3. **API-First & Storage Conservation**: Retrieve bounded, scientifically valid subsets; persist files into SeaweedFS only where justified.
4. **Public Access First**: Implement all open, unauthenticated endpoints immediately; segregate token-gated providers into `MANUAL_DATA_ACCESS_REGISTER.md`.
5. **Strict Idempotency**: Verify record existence by unique identifiers, SHA-256 hashes, and coordinate/time constraints before writing.

---

## 2. In-Scope Acquisitions (Public Access)

The following 5 acquisition targets will be executed immediately using unauthenticated, production-grade endpoints:

```
+----------------------------------------------------------------------------------------------------+
|                                    IN-SCOPE ACQUISITION TARGETS                                    |
+----------------------------------------------------------------------------------------------------+
  1. OCEAN COLOUR (CHLA)     --> NOAA CoastWatch ERDDAP ('nesdisVHNnoaa20chlaDaily')
  2. REAL eDNA & METAGENOMES --> EMBL-EBI MGnify ('mgnify-marine-biomes') & ENA ('ena-marine-runs')
  3. SEAFLOOR HABITATS       --> EMODnet Seabed Habitats OGC WFS ('emodnet_view:art17_hab_1170')
  4. REAL RESEARCH MEDIA     --> GBIF Open-Access Research Photography (CC-BY / AWS S3)
  5. BIODIVERSITY EXPANSION  --> OBIS & GBIF Indian Ocean Corals, Sea Turtles, and Elasmobranchs
+----------------------------------------------------------------------------------------------------+
```

---

### Target 1: Ocean Colour & Biogeochemistry (Chlorophyll-a)

- **Source / Provider**: NOAA CoastWatch ERDDAP (`https://coastwatch.pfeg.noaa.gov/erddap/griddap/nesdisVHNnoaa20chlaDaily`)
- **Dataset ID**: `nesdisVHNnoaa20chlaDaily`
- **Missing Variable**: `chla` (Chlorophyll-a concentration in $mg/m^3$, derived from NOAA-20 VIIRS Level 3 daily science quality).
- **Spatial Coverage**: Arabian Sea / Indian Ocean $[65.0^\circ\text{E}-75.0^\circ\text{E}, 10.0^\circ\text{N}-15.0^\circ\text{N}]$.
- **Temporal Coverage**: 2026-11-20 to 2026-11-25.
- **Destination Storage**:
  - NetCDF file: `s3://marine-raw/noaa/nesdisVHNnoaa20chlaDaily/...nc`
  - Database: `dataset_registry`, `ingestion_jobs`, `ingestion_assets`, `validation_reports`, `provenance_records`.
- **Validation Checks**:
  - CF-1.8 NetCDF conventions.
  - Physical value range check: $0.001 \le chla \le 100.0\text{ mg/m}^3$.
  - Coordinate continuity and non-empty mask.

---

### Target 2: Real Molecular & eDNA Archives (MGnify & ENA)

- **Source / Provider**: EMBL-EBI MGnify API (`https://www.ebi.ac.uk/metagenomics/api/v1`) & European Nucleotide Archive (ENA) Portal API (`https://www.ebi.ac.uk/ena/portal/api`)
- **Missing Data**: Real marine environmental metagenome study metadata, sample accessions, biome hierarchies, sequencing run accessions, read counts, and FASTQ FTP locations.
- **Target Studies**:
  - MGnify Marine Biome Study `MGYS00006861` (Marine metagenomic library of Baltic Sea).
  - ENA Marine Environmental Runs (`tax_eq(408172)`).
- **Destination Storage**:
  - Database: `edna_samples` (populating real `sample_code`, `expedition_id`, `water_body`, `sequencing_platform`, `target_gene`).
  - Taxonomic Reconciliation: Ingestion into `edna_taxonomic_assignments` linking to WoRMS AphiaID.
- **Validation Checks**:
  - Mandatory molecular presence disclaimer enforcement.
  - Valid BioSample and Run accession format verification (`SAM[NDEA][0-9]+`, `[DES]RR[0-9]+`).

---

### Target 3: Seafloor Geology & Benthic Habitats (EMODnet)

- **Source / Provider**: EMODnet Seabed Habitats OGC WFS (`https://ows.emodnet-seabedhabitats.eu/geoserver/emodnet_view/wfs`)
- **Missing Data**: Substrate classification, benthic habitat polygons, and marine conservation reef features (`art17_hab_1170` Reefs, Subtidal sandbanks).
- **Protocol**: OGC WFS 1.1.0 XML / GeoJSON feature streaming.
- **Destination Storage**:
  - Database: Relational & PostGIS persistence in `scientific_catalog_entries` and spatial geometry table.
- **Validation Checks**:
  - Valid OGC Simple Features geometry.
  - Coordinate system verification (EPSG:4326).

---

### Target 4: Real Research Marine Media (High-Resolution Field Imagery)

- **Source / Provider**: Open-access scientific research photography from GBIF occurrences (hosted on AWS S3 / `inaturalist-open-data`).
- **Missing Data**: Real high-resolution benthic / marine species photographs depicting real organisms with verified CC-BY / CC0 licences.
- **Target Species**:
  - *Chelonia mydas* (Green Sea Turtle) — Key marine megafauna.
  - *Rhincodon typus* (Whale Shark) — Endangered marine elasmobranch.
  - *Acanthaster planci* (Crown-of-thorns starfish) — Coral reef keystone predator.
- **Destination Storage**:
  - File: `s3://marine-media/images/YYYY/MM/...jpg`
  - Database: `marine_media_assets` (recording camera EXIF, exact lat/lon, depth, species name, and CC licence).
- **Validation Checks**:
  - Valid JPEG/PNG binary header and image dimension ($> 640 \times 480$).
  - Cryptographic SHA-256 calculation matching stored asset record.

---

### Target 5: Broader Marine Biodiversity (Indian Ocean Extension)

- **Source / Provider**: OBIS v3 API (`https://api.obis.org/v3`) & GBIF v1 API (`https://api.gbif.org/v1`)
- **Missing Data**: Critical Indian Ocean marine taxa currently absent from the database:
  - Scleractinian Corals: *Acropora digitifera* (Staghorn Coral), *Porites lutea*.
  - Marine Megafauna: *Chelonia mydas* (Green Sea Turtle).
  - Elasmobranchs: *Rhincodon typus* (Whale Shark).
- **Destination Storage**:
  - Database: `marine_species_occurrences` with PostGIS `POINT(lon, lat)` spatial indexing.
  - Taxonomy: Automatic verification and caching in `marine_taxa` and `taxonomy_lookup_cache`.
- **Validation Checks**:
  - Coordinate bounds check: Northern Indian Ocean $[60.0^\circ\text{E}-95.0^\circ\text{E}, -5.0^\circ\text{N}-25.0^\circ\text{N}]$.
  - Depth sanity check: $0 \le depth\_m \le 4000.0$.
  - Deduplication clustering ($< 1.0\text{ km}$ distance threshold).

---

## 3. Segregated Manual Access Targets

The following candidates require individual user registration, institutional approval, or API keys. They will **NOT** be mocked, faked, or bypassed; instead, they will be formally catalogued in `backend/MANUAL_DATA_ACCESS_REGISTER.md`:

| Candidate Source | Required Auth / Key | URL for User Registration | Feature Provided |
| :--- | :--- | :--- | :--- |
| **Global Fishing Watch (GFW)** | Bearer API Token | [globalfishingwatch.org/our-apis](https://globalfishingwatch.org/our-apis) | Apparent fishing effort, AIS vessel encounters, transshipment events |
| **Protected Planet (WDPA)** | API Token (`api.protectedplanet.net`) | [protectedplanet.net](https://www.protectedplanet.net) | Global Marine Protected Area (MPA) polygons and no-take zones |
| **Copernicus Marine Large Queries** | User Credentials | [marine.copernicus.eu](https://marine.copernicus.eu) | Unbounded multi-gigabyte physics and biogeochemical reanalysis |

---

## 4. Execution Roadmap

```
Step 1: Extend NOAA CoastWatch module for Chlorophyll-a (nesdisVHNnoaa20chlaDaily)
   |
Step 2: Implement EBI MGnify / ENA real marine eDNA study & run ingestion
   |
Step 3: Ingest real open-access CC-BY marine research media into S3 marine-media
   |
Step 4: Expand Indian Ocean biodiversity occurrences for corals & turtles
   |
Step 5: Verify idempotency (re-running operations produces zero duplicates)
   |
Step 6: Execute full regression test suite (ensure existing 108 tests pass)
```
