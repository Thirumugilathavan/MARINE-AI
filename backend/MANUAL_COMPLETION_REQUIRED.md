# SSTRIX MARINE-AI / SIH25041 — Manual Completion & Production Readiness Guide

**Document Version**: 2.0  
**Audit Date**: November 26, 2026  
**Auditor**: Lead Oceanographic Data Platform Architect & Infrastructure Auditor  
**Repository**: `https://github.com/Thirumugilathavan/MARINE-AI.git`  
**Active Branch**: `feature/marine-complete-backend-platform`  
**Commit**: `2d0165a`  

---

## 1. Overview & Scope Boundaries

This document provides a transparent, exhaustive checklist of external credentials, environment-specific security certificates, real-world scientific datasets (media and sequencing archives), and production configurations that require manual intervention by the platform administrator or scientific user.

All backend code, FastAPI REST APIs, PostgreSQL/PostGIS database schemas, SeaweedFS S3 object storage buckets, and automated tests (108/108 passing) are fully implemented, verified, and operational. The items below represent external physical, scientific, or organizational dependencies that cannot or should not be automated without external accounts or heavy data transfers.

---

## 2. External Credentials & Secret Configuration

| Service / Provider | Config Variable (`.env`) | Default / Current Status | Action Required by User | Impact if Not Configured |
| :--- | :--- | :--- | :--- | :--- |
| **Copernicus Marine Service** | `COPERNICUS_USERNAME`<br>`COPERNICUS_PASSWORD` | Set in `.env` / Unverified external subscription | Create a free account at [marine.copernicus.eu](https://marine.copernicus.eu). Verify credentials by running `copernicusmarine login --username <USER> --password <PASS>`. | Unauthenticated live queries will fail or fall back to cached local staging samples. |
| **SeaweedFS S3 Secrets** | `SEAWEEDFS_ACCESS_KEY`<br>`SEAWEEDFS_SECRET_KEY` | `sstrix_marine_access`<br>`sstrix_marine_secret` | If deploying outside local Docker, update with production IAM credentials and rotate keys. | Production storage access requires production credentials. |
| **PostgreSQL / PostGIS** | `DATABASE_USER`<br>`DATABASE_PASSWORD`<br>`DATABASE_NAME` | `postgres`<br>`postgres`<br>`sstrix_marine` | Update for production database clusters; never use default passwords in public environments. | Database security and access control. |
| **Application Secret Key** | `SECRET_KEY`<br>`APP_ENV` | `production` / Default key | Generate a secure 256-bit random hex key for JWT session signing. | API security and token integrity. |

---

## 3. SSL & Trust Store Configuration (INCOIS Certificate)

* **Current Status**: Development SSL bypass enabled for INCOIS ERDDAP endpoints (`incois_verify_ssl=False` with explicit security logging).
* **Reason**: INCOIS (Indian National Centre for Ocean Information Services) endpoints (`incois.gov.in`) use SSL certificates issued by the Indian National Informatics Centre (NIC) / Controller of Certifying Authorities (CCA) root CA. This root certificate is not included in standard Debian / certifi bundles by default.
* **Production Resolution Procedure**:
  1. Download the official Indian CCA Root Certificate from [cca.gov.in](https://cca.gov.in) (`cca_root.crt`).
  2. Install the certificate in the host trust store:
     - **Ubuntu/Debian**:
       ```bash
       sudo cp cca_root.crt /usr/local/share/ca-certificates/nic_root.crt
       sudo update-ca-certificates
       ```
     - **Windows Server**:
       ```powershell
       certutil -addstore -f "ROOT" cca_root.crt
       ```
  3. Set `INCOIS_VERIFY_SSL=True` and configure `INCOIS_SSL_CA_BUNDLE` in `backend/.env`.

---

## 4. Real Environmental DNA (eDNA) Raw Sequencing Data Acquisition

* **Current Status**: The backend provides the complete sample registry, metadata storage, FASTQ/FASTA S3 persistence in `marine-edna`, ASV taxonomic assignment schema, and WoRMS AphiaID reconciliation with non-definitive presence safeguards. Storage currently contains two 106-byte synthetic single-read FASTQ fixtures for pipeline verification.
* **Scope Boundary**: Multi-gigabyte paired-end Illumina (HiSeq/NovaSeq) or Oxford Nanopore raw sequencing archives were not checked into git or downloaded into local storage to avoid multi-gigabyte repository bloat.
* **Procedure to Ingest Real High-Throughput eDNA Datasets**:
  1. Download real marine eDNA raw sequencing reads from public repositories:
     - **NCBI SRA**: E.g., BioProject PRJNA576435 (Tara Oceans Marine Microbiome), PRJNA674843 (Indian Ocean Coral Reef eDNA).
     - Use SRA Toolkit:
       ```bash
       fasterq-dump SRR12345678 --split-files --gzip -O /path/to/downloads/
       ```
  2. Upload raw paired-end FASTQ archives to the platform using the eDNA API:
     ```bash
     curl -X POST "http://127.0.0.1:8000/api/v1/edna/samples/upload" \
          -H "accept: application/json" \
          -H "Content-Type: multipart/form-data" \
          -F "file=@SRR12345678_1.fastq.gz;type=application/gzip" \
          -F "sample_code=EDNA-IND-2026-001" \
          -F "target_gene=12S" \
          -F "latitude=15.25" \
          -F "longitude=68.50"
     ```
  3. Process amplicon sequence variants (ASVs) via external high-throughput pipelines (e.g. Nextflow `nf-core/ampliseq` with DADA2) and register taxonomic assignments via `POST /api/v1/edna/samples/{sample_id}/assignments`.

---

## 5. Real Underwater ROV Videos and High-Resolution Benthic Imagery

* **Current Status**: **NO REAL UNDERWATER VIDEOS EXIST IN STORAGE.** Storage contains one 55-byte synthetic MP4 container header fixture and three image test stubs.
* **Scope Boundary**: High-definition (1080p / 4K) ROV dive footage requires gigabytes of bandwidth and dedicated storage allocation.
* **Procedure to Ingest Real Underwater ROV Media**:
  1. Acquire open-access deep-sea ROV dive video footage:
     - **NOAA Ocean Exploration Video Portal**: [oceanexplorer.noaa.gov](https://oceanexplorer.noaa.gov) (Oceano/Deepwater Exploration MP4 clips).
     - **Schmidt Ocean Institute**: Open-access 4K benthic transect video archives.
  2. Ingest video assets into SeaweedFS `marine-media` bucket via the Media API:
     ```bash
     curl -X POST "http://127.0.0.1:8000/api/v1/media/upload" \
          -H "accept: application/json" \
          -H "Content-Type: multipart/form-data" \
          -F "file=@dive_transect_01.mp4;type=video/mp4" \
          -F "media_type=video" \
          -F "latitude=12.45" \
          -F "longitude=74.15" \
          -F "depth_meters=850.0" \
          -F "camera_sensor_info=Insite Pacific Zeus Plus HD ROV Camera"
     ```
  3. The platform will automatically extract file metadata, calculate SHA-256 integrity hashes, generate S3 presigned URLs, and index geospatial capture coordinates in PostGIS.

---

## 6. GEBCO Full 15-Arc-Second Global Bathymetry Grid (Offline Option)

* **Current Status**: The backend provides sub-second point and bounding-box depth lookups via the NOAA NCEI DEM Global Mosaic ImageServer REST API (`gis.ngdc.noaa.gov`), which embeds the official GEBCO 2023 grid.
* **Optional Offline Grid Deployment**: If the platform must operate in completely air-gapped or disconnected environments without internet access to NOAA NCEI:
  1. Download the full GEBCO 2023 Grid NetCDF (approx. 30 GB uncompressed, 8 GB compressed) from [gebco.net](https://www.gebco.net/data_and_products/gridded_bathymetry_data/).
  2. Place the NetCDF file in `backend/dataset-staging/gebco/GEBCO_2023.nc`.
  3. Configure `GEBCO_LOCAL_NETCDF_PATH` in `.env` to enable local `xarray` raster slicing.

---

## 7. Production Infrastructure, Domain Routing & TLS

* **Current Status**: Operational on local Docker stack (`127.0.0.1:5432` PostGIS, `127.0.0.1:8333` SeaweedFS S3, `127.0.0.1:8000` FastAPI).
* **Production Deployment Steps**:
  1. **Nginx Reverse Proxy & SSL**:
     Deploy Nginx or Caddy with Let's Encrypt automated TLS certificates for public endpoints:
     ```nginx
     server {
         listen 443 ssl http2;
         server_name api.marine-ai.org;
         
         ssl_certificate /etc/letsencrypt/live/api.marine-ai.org/fullchain.pem;
         ssl_certificate_key /etc/letsencrypt/live/api.marine-ai.org/privkey.pem;

         client_max_body_size 500M;

         location / {
             proxy_pass http://127.0.0.1:8000;
             proxy_set_header Host $host;
             proxy_set_header X-Real-IP $remote_addr;
             proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
             proxy_set_header X-Forwarded-Proto $scheme;
         }
     }
     ```
  2. **CORS Origins**:
     Update `CORS_ORIGINS` in `backend/app/core/config.py` to permit only the authorized production frontend origin (e.g. `https://marine-ai.org`).
  3. **Database Backups**:
     Configure automated daily PostgreSQL backups using `pg_dump`:
     ```bash
     pg_dump -Fc -h 127.0.0.1 -U postgres sstrix_marine > /backup/marine_db_$(date +%Y%m%d).dump
     ```

---

## 8. Frontend Application Development

* **Current Status**: **STRICTLY NOT STARTED**.
* **Reason**: Explicit scope boundary for this backend milestone (data ingestion, normalization, database persistence, object storage, and acceptance audit only).
* **Documentation for Frontend Team**:
  The backend provides complete interactive OpenAPI specifications and schemas:
  - **Swagger UI**: `http://127.0.0.1:8000/docs`
  - **ReDoc**: `http://127.0.0.1:8000/redoc`
  - **OpenAPI JSON**: `http://127.0.0.1:8000/openapi.json`
* **Available Endpoint Groups**:
  - `/api/v1/catalogue` (Dataset discovery & provider registry)
  - `/api/v1/ingestion` (Job orchestration, triggering, status tracking)
  - `/api/v1/oceanography` (CTD, ADCP, hydrographic profiles)
  - `/api/v1/biodiversity` (OBIS & GBIF species occurrences, bounding box filters)
  - `/api/v1/taxonomy` (WoRMS taxonomic lookup, AphiaID reconciliation)
  - `/api/v1/edna` (Sample registry, ASV taxonomic assignment)
  - `/api/v1/media` (Underwater video & benthic imagery metadata and streaming)
  - `/api/v1/fisheries` (FAO national capture and aquaculture statistics)
