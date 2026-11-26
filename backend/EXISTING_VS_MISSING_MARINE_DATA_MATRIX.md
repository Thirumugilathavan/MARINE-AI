# SSTRIX MARINE-AI / SIH25041 — Existing vs. Missing Marine Data Matrix

**Audit Date**: November 26, 2026  
**Investigator**: Lead Oceanographic Data Platform Architect  
**Repository**: `https://github.com/Thirumugilathavan/MARINE-AI.git`  
**Active Branch**: `feature/marine-complete-backend-platform`  
**Baseline Git Commit**: `3b057d7`  

---

## 1. Executive Summary & Audit Methodology

This matrix provides an evidence-based comparison between the existing, verified data foundation of the **MARINE-AI** platform and the candidate marine datasets across 10 critical oceanographic and environmental domains.

### Cardinal Rule Adherence
- **Zero Duplication**: No existing dataset, variable, observation, NetCDF file, database table, or API route is re-created, overwritten, or re-downloaded.
- **Evidence-Based Baseline**: Classification is grounded strictly in live database row counts (PostgreSQL 17.5 / PostGIS 3.5.2) and verified SeaweedFS S3 objects.
- **Controlled Status Vocabulary**: Every candidate domain and dataset is evaluated with the required status taxonomy:
  - `already_integrated_and_verified`
  - `integrated_but_no_real_data`
  - `metadata_only`
  - `partially_covered`
  - `missing_dataset`
  - `missing_geographic_coverage`
  - `missing_temporal_coverage`
  - `missing_variables`
  - `missing_file_assets`
  - `requires_human_access`
  - `unverified`

---

## 2. Complete Existing Data Baseline

| Storage / Subsystem | Current Stored Entity | Exact Verified Count / Size | Content & Coverage Summary |
| :--- | :--- | :--- | :--- |
| **PostgreSQL Database** | `data_providers` | 5 rows | Core physical ocean providers (`copernicus`, `noaa`, `argo`, `incois`, `gebco`). |
| **PostgreSQL Database** | `scientific_catalog_entries` | 10 rows | Central catalogue covering 9 providers with 7-stage lifecycle state engine. |
| **PostgreSQL Database** | `ingestion_jobs` | 29 rows | Job records (28 `COMPLETED`, 1 `RUNNING`). |
| **PostgreSQL Database** | `ingestion_assets` | 22 rows | Verified NetCDF assets linked to jobs. |
| **PostgreSQL Database** | `validation_reports` | 21 rows | NetCDF CF-1.8 and statistical validation logs. |
| **PostgreSQL Database** | `provenance_records` | 19 rows | W3C PROV-O SHA-256 cryptographic lineage records. |
| **PostgreSQL / PostGIS** | `marine_species_occurrences` | 14 rows | 9 OBIS (*Thunnus albacares*) + 5 GBIF (*Balaenoptera musculus* off Sri Lanka). |
| **PostgreSQL Database** | `marine_taxa` | 1 row | Accepted WoRMS authority record for *Thunnus albacares* (AphiaID 127027). |
| **PostgreSQL Database** | `taxonomy_lookup_cache` | 1 row | Case-insensitive cache for high-throughput WoRMS name resolution. |
| **PostgreSQL / PostGIS** | `oceanographic_profiles` | 2 rows | Station AS01 profiles (1 CTD cast + 1 ADCP transect). |
| **PostgreSQL Database** | `oceanographic_observations` | 9 rows | 5 CTD depth levels (1m to 100m) + 4 ADCP velocity bins (5m to 35m). |
| **PostgreSQL Database** | `fisheries_statistics` | 8 rows | FAO baseline annual capture & aquaculture statistics for IND, MDV, LKA (2021-2023). |
| **PostgreSQL Database** | `edna_samples` | 4 rows | 1 synthetic fixture with FastQ link + 3 audit stubs. |
| **PostgreSQL Database** | `edna_taxonomic_assignments` | 3 rows | AphiaID 127027 assignments with mandatory non-definitive presence safeguards. |
| **PostgreSQL Database** | `marine_media_assets` | 4 rows | 1 synthetic JPEG, 1 synthetic MP4 container header, 2 audit text payloads. |
| **SeaweedFS S3 Storage** | `s3://marine-raw` | 5 objects (52,940 B) | 4 real NetCDF files (Argo, INCOIS, NOAA OISST) + 1 bootstrap canary. |
| **SeaweedFS S3 Storage** | `s3://marine-research` | 3 objects (535 B) | 2 CTD CSVs (206 B each) + 1 ADCP CSV (123 B). |
| **SeaweedFS S3 Storage** | `s3://marine-media` | 4 objects (1,966 B) | 1 synthetic 55 B MP4 container + 1 synthetic 1,829 B JPEG + 2 text stubs. |
| **SeaweedFS S3 Storage** | `s3://marine-edna` | 2 objects (212 B) | 2 synthetic 106 B FASTQ.gz fixtures (single 60 bp amplicon read). |
| **Local Staging Folders**| `dataset-staging` & `backend/staging` | 24 NetCDF files (422 KB) | 4 Copernicus (`thetao`), 6 Argo (`temp`, `psal`), 5 INCOIS (`wind_speed`), 9 NOAA (`sst`). |

---

## 3. Comprehensive Domain-by-Domain Difference Matrix

The following matrix records every existing integration and evaluates all candidate candidate datasets across domains A through J:

| Domain | Candidate Source / Provider | Dataset Identifier | Variables | Geographic Coverage | Temporal Coverage | Depth Coverage | Resolution | Existing Records / Files Stored | Existing Ingestion Status | Current Status | Missing Coverage / Gaps | Required Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Physical Oceanography** | Copernicus Marine Service | `cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m` | `thetao` (Potential Temp) | Global / Bay of Bengal $[80^\circ\text{E}-90^\circ\text{E}, 10^\circ\text{N}-15^\circ\text{N}]$ | 2026-11-20 to 2026-11-25 | 0.5m to 5.0m | 0.083° (approx. 9 km), Daily | 4 NetCDF files in staging (95.3 KB); 0 in S3 | Full OPeNDAP/MDS client implemented & verified | `already_integrated_and_verified` | Multi-parameter variables (`so`, `zos`) not downloaded | **Preserve.** Do not duplicate. Extend variables only if needed. |
| **Physical Oceanography** | NOAA CoastWatch ERDDAP | `ncdcOisst21Agg` | `sst` (SST), `anom` (Anomaly) | Global / Arabian Sea $[65^\circ\text{E}-75^\circ\text{E}, 10^\circ\text{N}-20^\circ\text{N}]$ | 2026-11-01 to 2026-11-20 | Sea surface | 0.25°, Daily | 9 NetCDFs in staging (123.8 KB); 2 NetCDFs in S3 `marine-raw` (26.5 KB) | Full Griddap ERDDAP client implemented & verified | `already_integrated_and_verified` | None for SST | **Preserve.** Do not duplicate. |
| **Physical Oceanography** | Argo Float Network (Ifremer GDAC) | `ArgoFloats` | `temp`, `psal`, `pres` | Indian Ocean $[60^\circ\text{E}-75^\circ\text{E}, 0^\circ\text{N}-10^\circ\text{N}]$ | 2026-10-01 to 2026-11-20 | 0 to 2000 dbar | Float profiling cycles (in-situ) | 6 NetCDFs in staging (139.1 KB); 1 NetCDF in S3 `marine-raw` (15.3 KB) | Full Tabledap ERDDAP client implemented & verified | `already_integrated_and_verified` | BGC Argo sensors (O2, pH, nitrate) not integrated | **Preserve.** Do not duplicate. |
| **Physical Oceanography** | INCOIS MoES ERDDAP | `ascat_daily_datasets` | `wind_speed`, `wind_stress` | Bay of Bengal $[80^\circ\text{E}-92^\circ\text{E}, 8^\circ\text{N}-20^\circ\text{N}]$ | 2026-11-01 to 2026-11-15 | 10m surface | 0.25°, Daily | 5 NetCDFs in staging (63.9 KB); 1 NetCDF in S3 `marine-raw` (11.0 KB) | Full Griddap ERDDAP client with SSL bypass | `already_integrated_and_verified` | Waves (`swh`, `mwp`) not ingested | **Preserve.** Do not duplicate. |
| **Seafloor Topography** | GEBCO / NOAA NCEI | `DEM_extents/ImageServer` | Water depth / elevation (m) | Global continuous coverage | 2023 grid release | Benthic surface | 15 arc-seconds (approx. 450 m) | Dynamic REST queries (e.g. -3979.0m at 15°N, 68°E) | Full ArcGIS ImageServer REST client implemented | `already_integrated_and_verified` | Local static grid files not downloaded | **Preserve API-first access.** Do not download 30GB grid. |
| **Biodiversity** | OBIS | `obis-v3-occurrences` | Occurrences, coordinates, taxonomy, depth | Indian Ocean $[60^\circ\text{E}-90^\circ\text{E}, 0^\circ\text{N}-25^\circ\text{N}]$ | Historical to 2023 | Surface to 200m | Point occurrence | 9 rows in `marine_species_occurrences` (*Thunnus albacares*) | Full REST client & PostGIS spatial persistence | `partially_covered` | Missing major marine groups (corals, sea turtles, elasmobranchs) | **Extend.** Ingest missing taxa in Indian Ocean. |
| **Biodiversity** | GBIF | `gbif-v1-occurrences` | Occurrences, basis of record, coordinates | Northern Indian Ocean / Sri Lanka | 2024 records | Surface / coastal | Point occurrence | 5 rows in `marine_species_occurrences` (*Balaenoptera musculus*) | Full REST client & PostGIS spatial persistence | `partially_covered` | Missing coral reef and mangrove keystone species | **Extend.** Ingest missing taxa in Indian Ocean. |
| **Taxonomy** | WoRMS | `worms-aphia-registry` | AphiaID, accepted valid name, classification | Global marine taxa | Current dynamic authority | All depths | Taxon entity | 1 taxon (*Thunnus albacares*) + 1 cached lookup | Full Aphia REST client & relational cache | `already_integrated_and_verified` | Additional taxa resolved dynamically on demand | **Preserve.** Do not duplicate. Cache new taxa automatically. |
| **Fisheries** | FAO Fisheries | `fao-fishstat-catch` | Capture & aquaculture tonnage | India, Maldives, Sri Lanka (FAO Area 51, 57) | 2021 to 2023 | Surface/Commercial | National annual aggregate | 8 rows in `fisheries_statistics` | Full relational model, seed sync & WFS area client | `already_integrated_and_verified` | Additional littoral states (Seychelles, Mauritius) | **Preserve.** Do not duplicate. |
| **Fishing Activity (A)** | Global Fishing Watch (GFW) | `gfw-apparent-fishing-effort` | Apparent fishing effort (hours), AIS vessel tracks | Global / EEZ boundaries | 2012 to 2024 | Surface | 0.01° / 0.1° raster & vessel events | 0 records | Not implemented | `requires_human_access` | Requires Bearer API key via user registration at `globalfishingwatch.org/our-apis` | **Register in `MANUAL_DATA_ACCESS_REGISTER.md`.** Do not mock. |
| **Imagery & Video (B)** | FathomNet / MBARI | `fathomnet-benthic-images` | ROV benthic imagery, bounding box annotations | Global benthic dives | 1988 to present | 100m to 4000m | High-res imagery ($1920\times1080$) | 0 records | Not implemented | `requires_human_access` | Cloudflare bot challenge / 429 rate limit blocks headless automated access | **Register in `MANUAL_DATA_ACCESS_REGISTER.md`.** |
| **Imagery & Video (B)** | GBIF Open-Access Research Photography | `gbif-marine-media` | High-res scientific field photography, CC licences, coordinates | Indian Ocean / Tropical Indo-Pacific | 2020 to 2024 | Coastal / Benthic | High-res ($1024\times768$ to $4000\times3000$) | 0 real photos (only 1 synthetic PIL JPEG and 2 text stubs) | Media upload endpoint exists, but lacks automated crawler | `missing_file_assets` | Storage lacks real research imagery | **Implement.** Ingest real open-access CC-BY scientific marine photos into S3 `marine-media`. |
| **Imagery & Video (B)** | NOAA Ocean Exploration (OER) | `noaa-oer-dive-videos` | Real ROV deep-sea dive video footage (MP4) | US EEZ, Pacific, Atlantic seamounts | 2010 to present | 200m to 6000m | 720p / 1080p MP4 | 0 real videos (only 1 synthetic 55 B container header) | Endpoint exists | `missing_file_assets` | Platform has NO real underwater research videos | **Document in manual register;** provide sample ingestion path. |
| **eDNA Archives (C)** | EMBL-EBI MGnify | `mgnify-marine-biomes` | Marine metagenomic studies, sample metadata, biomes | Global marine biomes (Baltic, Atlantic, Indian Ocean) | 2015 to 2024 | Epipelagic to Bathypelagic | Study / Sample level | 0 records | Not implemented | `missing_dataset` | Platform lacks real marine metagenomic and microbiome study metadata | **Implement.** Connect to MGnify REST API, ingest real marine studies into `edna_samples`. |
| **eDNA Archives (C)** | EBI European Nucleotide Archive (ENA) | `ena-marine-runs` | Sample accessions, run accessions, read counts, FASTQ FTP URLs | Global marine environmental samples (`tax_eq(408172)`) | 2015 to 2024 | All depths | BioSample / Read Run | 0 real sequencing runs (only two 106 B synthetic fixtures) | FASTQ parser exists, but no real run metadata | `missing_file_assets` | Platform lacks real marine environmental sequencing metadata | **Implement.** Connect to ENA REST API, ingest real marine run records and study accessions. |
| **Biogeochemistry (D)** | NOAA CoastWatch ERDDAP | `nesdisVHNnoaa20chlaDaily` | `chla` (Chlorophyll-a, $mg/m^3$) | Global / Indian Ocean $[60^\circ\text{E}-90^\circ\text{E}, 0^\circ\text{N}-25^\circ\text{N}]$ | 2017 to present (Daily) | Sea surface | 4 km, Daily Level 3 | 0 records | NOAA provider exists, but lacks Chlorophyll-a dataset registration | `missing_variables` | Platform completely lacks Chlorophyll-a observation data | **Implement.** Extend NOAA provider to register `nesdisVHNnoaa20chlaDaily` and ingest real sample. |
| **Waves & Currents (E)** | INCOIS MoES ERDDAP | `incois_wave_model` / `AMSR2_3day_Global` | `swh` (Significant Wave Height), `mwp` (Mean Wave Period) | North Indian Ocean | 2020 to present | Sea surface | 0.25°, 3-day / daily | 0 records | INCOIS provider exists, but lacks wave dataset registration | `missing_variables` | Wave dynamics currently absent | **Implement.** Register wave dataset and ingest sample into S3 `marine-raw`. |
| **Research Surveys (F)** | SeaDataNet / PANGAEA / BODC | `pangaea-marine-ctd-cruises` | Calibrated CTD bottles, bottle nutrients, rosette casts | Global oceanographic cruises | 1970 to present | 0 to 6000m | Cruise station profiles | 2 local CSVs (synthetic audit stations) | CTD/ADCP CSV parsers implemented | `missing_file_assets` | Real open-access cruise profile files missing | **Ingest.** Acquire real open-access CTD cruise profile into S3 `marine-research`. |
| **Seafloor Habitats (G)** | EMODnet Seabed Habitats | `emodnet-seabed-habitats-wfs` | Benthic habitat types, substrate classes, biozones | European seas & North Atlantic | 2018 to 2023 | Seafloor | OGC WFS 1:250,000 spatial polygons | 0 records | Not implemented | `missing_dataset` | Seafloor substrate classification missing | **Implement.** Connect to EMODnet WFS, retrieve and index real benthic habitat polygons. |
| **Conservation (H)** | Protected Planet (WDPA) | `wdpa-marine-protected-areas` | MPA boundaries, IUCN category, governance, no-take status | Global MPAs / Indian Ocean MPAs | Current 2024 release | Coast to EEZ | Spatial vector polygons | 0 records | Not implemented | `requires_human_access` | WDPA API requires token registration (`api.protectedplanet.net`) | **Register in `MANUAL_DATA_ACCESS_REGISTER.md`.** |
| **Pollution (J)** | NOAA Marine Debris / EMODnet Chemistry | `emodnet-marine-litter` | Floating macro-litter, beach litter, seafloor litter | Regional seas | 2015 to 2023 | Surface to seafloor | Point surveys | 0 records | Not implemented | `missing_dataset` | Marine pollution & litter currently unaddressed | **Evaluate & document in missing plan.** |

---

## 4. Prioritized Implementation Actions

Based on this matrix, the following **genuinely missing** data components are scheduled for immediate public implementation:

1. **Ocean Colour & Biogeochemistry**: Extend NOAA CoastWatch provider with dataset `nesdisVHNnoaa20chlaDaily` to ingest real Chlorophyll-a data into S3 `marine-raw`.
2. **Real Molecular & eDNA Archives**: Implement EBI MGnify / ENA connector to ingest real marine environmental metagenome study metadata and sequencing accessions into `edna_samples`.
3. **Seafloor Geology & Marine Habitats**: Implement EMODnet Seabed Habitats WFS connector to ingest real benthic habitat polygons and substrate types.
4. **Real Marine Research Media**: Ingest real high-resolution CC-BY research photographs of marine taxa into S3 `marine-media` and register in `marine_media_assets`.
5. **Broader Biodiversity Occurrences**: Ingest missing Indian Ocean marine groups (corals, sea turtles, elasmobranchs) via existing OBIS and GBIF connectors.
6. **Manual Credentials Register**: Formally document Global Fishing Watch (GFW), Protected Planet (WDPA), and high-volume ROV streaming in `backend/MANUAL_DATA_ACCESS_REGISTER.md`.
