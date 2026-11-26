# MARINE-AI / SIH25041 — MANUAL COMPLETION & ACTION REQUIRED

This document provides a transparent, exhaustive checklist of external credentials, environment-specific installations, and production configurations that require manual intervention by the platform administrator or user.

All code, backend REST APIs, database schemas, object storage buckets, and automated tests are fully implemented, verified, and operational. The items below represent external physical or organizational dependencies that cannot or should not be automated programmatically.

---

## 1. External Credentials & Secret Configuration

| Provider / Service | Config Variable (`.env`) | Default / Current Status | Action Required by User | Impact if Not Configured |
| :--- | :--- | :--- | :--- | :--- |
| **Copernicus Marine Service** | `COPERNICUS_USERNAME`<br>`COPERNICUS_PASSWORD` | Set in `.env` / Unverified external subscription | Ensure account is active on [marine.copernicus.eu](https://marine.copernicus.eu) with access to NRT/MY physics products. | Unauthenticated requests will fail for Copernicus-specific datasets. |
| **SeaweedFS S3 Secrets** | `SEAWEEDFS_ACCESS_KEY`<br>`SEAWEEDFS_SECRET_KEY` | `sstrix_marine_access`<br>`sstrix_marine_secret` | If deploying outside local Docker, update with production IAM credentials and rotate keys. | Production storage access requires production credentials. |
| **PostgreSQL Credentials** | `POSTGRES_USER`<br>`POSTGRES_PASSWORD`<br>`POSTGRES_DB` | `postgres`<br>`postgres`<br>`sstrix_marine` | Update for production database clusters; never use default passwords in public environments. | Database security. |

---

## 2. SSL & Trust Store Configuration (INCOIS Certificate)

* **Current Status**: Development SSL bypass enabled for INCOIS ERDDAP/OPeNDAP endpoints (`verify=False` with explicit security logging).
* **Reason**: INCOIS (Indian National Centre for Ocean Information Services) endpoints (`incois.gov.in`) use certificates signed by the Indian National Informatics Centre (NIC) / Controller of Certifying Authorities (CCA) root CA, which is not included in standard Debian / certifi bundles by default.
* **Action Required for Production**:
  1. Download the official Indian CCA Root Certificate from [cca.gov.in](https://cca.gov.in).
  2. Install the certificate in the host operating system trust store (`/usr/local/share/ca-certificates/` on Linux or Windows Certificate Store).
  3. Re-enable strict SSL verification in `backend/app/modules/data_sources/incois/service.py` by removing `verify=False`.

---

## 3. High-Performance Bioinformatic Pipelines (eDNA)

* **Current Status**: The backend provides the complete sample registry, metadata storage, FASTQ/FASTA S3 persistence in `marine-edna`, ASV taxonomic assignment schema, and WoRMS AphiaID reconciliation with mandatory non-definitive presence safeguards.
* **Scope Boundary**: Raw FASTQ sequence alignment and denoising (e.g. running DADA2, QIIME2, or BLAST+ against custom marker databases) requires substantial HPC / GPU resources.
* **Action Required by User**:
  1. Process raw FASTQ files using standard bioinformatic pipelines (e.g. Nextflow `nf-core/ampliseq`).
  2. Ingest the resulting ASV table into the platform using `POST /api/v1/edna/samples/{sample_id}/assignments`.
  3. The platform will automatically validate species names against WoRMS and record authoritative AphiaIDs and safeguards.

---

## 4. Frontend Application

* **Current Status**: **STRICTLY NOT STARTED**.
* **Reason**: Explicit scope boundary specified for this phase (Backend platform, data pipelines, database, storage, and acceptance audit only).
* **API Documentation**: The backend FastAPI service serves full interactive OpenAPI documentation at:
  - Swagger UI: `http://127.0.0.1:8000/docs`
  - ReDoc: `http://127.0.0.1:8000/redoc`
* **Action Required by User**:
  - The frontend development team can develop the UI against the complete REST endpoints documented in OpenAPI.

---

## 5. Production Infrastructure & Domain Routing

* **Current Status**: Operational on local Docker Compose stack (`127.0.0.1:5432` for PostGIS, `127.0.0.1:8333` for SeaweedFS S3, `127.0.0.1:8000` for FastAPI).
* **Action Required for Production**:
  1. Set up an Nginx or Caddy reverse proxy with valid Let's Encrypt TLS/SSL certificates for public HTTPS access.
  2. Configure DNS records for the API subdomain (e.g., `api.marine-ai.org`).
  3. Set `CORS_ORIGINS` in `backend/app/core/config.py` to match the official production frontend domain.
