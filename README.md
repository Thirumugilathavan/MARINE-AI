# MARINE-AI Platform

An enterprise-grade Marine Artificial Intelligence and Oceanographic Data Platform engineered for multi-source ocean data ingestion, spatial indexing, analysis, and discovery.

---

## 1. Project Overview

The **MARINE-AI Platform** serves as an intelligent backend infrastructure for marine researchers, oceanographers, and maritime systems. It aggregates, standardizes, validates, and stores diverse oceanographic datasets—including physical ocean parameters, biogeochemical indicators, satellite observations, and in-situ sensor data.

Key capabilities:
- **FastAPI Core**: High-performance asynchronous REST API framework.
- **Spatio-temporal Database**: PostgreSQL 17 with PostGIS 3.5 for indexing ocean geometries, tracks, and spatial points.
- **S3-Compatible Object Store**: Local SeaweedFS distributed object store providing 7 dedicated marine storage buckets.
- **Marine Data Provider Integrations**: Copernicus Marine Service catalogue search, with NOAA, INCOIS, and Argo connectors in active development.

---

## 2. Platform Architecture

```
+-------------------------------------------------------------------------+
|                        FastAPI Application Layer                        |
|                                                                         |
|  +--------------------+  +----------------------+  +-----------------+  |
|  |  Health & Status   |  | Copernicus Discovery |  | Provider Routes |  |
|  |   / & /health      |  |  /api/v1/data-sources|  |   (In Progress) |  |
|  +--------------------+  +----------------------+  +-----------------+  |
+-------------------+-----------------------------------+-----------------+
                    |                                   |
                    v                                   v
+------------------------------------+ +----------------------------------+
|      PostgreSQL / PostGIS          | |      SeaweedFS S3 Storage        |
|  - Spatial tables & ocean metrics  | |  - marine-raw                    |
|  - Ingestion provenance & logs     | |  - marine-curated                |
|  - Database: sstrix_marine         | |  - marine-derived                |
|  - Port: 5432                      | |  - marine-media, edna, models... |
+------------------------------------+ +----------------------------------+
```

---

## 3. Directory Structure

```
D:\SSTRIX_MARINE_PLATFORM\
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       └── marine_data.py          # Marine data endpoints
│   │   ├── core/
│   │   │   └── config.py                   # Pydantic Settings & env configuration
│   │   ├── database/
│   │   │   └── connection.py               # SQLAlchemy PostgreSQL/PostGIS engine
│   │   ├── modules/
│   │   │   ├── catalogue/                  # Metadata catalogue modules
│   │   │   ├── data_sources/
│   │   │   │   └── copernicus/
│   │   │   │       └── service.py          # Copernicus Marine describe() service
│   │   │   ├── ingestion/                  # Ocean data ingestion pipelines
│   │   │   └── validation/                 # Quality indicators & validation
│   │   ├── storage/
│   │   │   └── s3_client.py                # Boto3 client for SeaweedFS S3
│   │   └── main.py                         # FastAPI application entrypoint
│   ├── tests/
│   │   └── test_api.py                     # API test suite (unittest/pytest)
│   ├── workers/                            # Async background task workers
│   ├── .env.example                        # Backend environment template
│   ├── .gitignore                          # Backend gitignore rules
│   └── requirements.txt                    # Reproducible Python dependencies
├── config/
│   ├── s3.json.example                     # SeaweedFS identity configuration template
│   └── s3.json                             # (Ignored) Local credentials
├── database-backups/                       # (Ignored) Database dump storage
├── dataset-staging/                        # (Ignored) Temporary dataset staging
├── postgres-data/                          # (Ignored) Local PostgreSQL persistent volume
├── project-documents/                      # Architecture notes & specs
│   └── README.md
├── seaweedfs-data/                         # (Ignored) Local SeaweedFS persistent volume
├── .env.example                            # Root environment template
├── .gitignore                              # Root security & ignore configuration
├── CONTRIBUTING.md                         # Teammate collaboration & branching guide
├── create_buckets.py                       # Provision SeaweedFS storage buckets
├── storage_test.py                         # SeaweedFS upload/download verification
└── test_s3.py                              # S3 connectivity check script
```

---

## 4. Local Infrastructure (Docker Setup)

The platform relies on two containerized infrastructure services running locally. Each teammate operates their own isolated Docker containers:

### A. PostgreSQL 17 with PostGIS 3.5
- **Container Name**: `sstrix-postgres`
- **Docker Image**: `postgis/postgis:17-3.5`
- **Host Port Binding**: `127.0.0.1:5432 -> 5432`
- **Database**: `sstrix_marine`
- **User**: `sstrix_admin`
- **Persistent Volume**: Local mount to `postgres-data/`

To launch locally if not already running:
```bash
docker run -d \
  --name sstrix-postgres \
  -e POSTGRES_DB=sstrix_marine \
  -e POSTGRES_USER=sstrix_admin \
  -e POSTGRES_PASSWORD=your_secure_password \
  -p 127.0.0.1:5432:5432 \
  -v ${PWD}/postgres-data:/var/lib/postgresql/data \
  postgis/postgis:17-3.5
```

### B. SeaweedFS Distributed Object Store
- **Container Name**: `sstrix-seaweedfs`
- **Host Port Binding**: `127.0.0.1:8333 -> 8333` (S3 API)
- **Persistent Volume**: Local mount to `seaweedfs-data/`

To configure SeaweedFS credentials locally:
1. Copy `config/s3.json.example` to `config/s3.json`.
2. Populate your local `accessKey` and `secretKey`.
3. Run `python create_buckets.py` to create the standard 7 marine buckets:
   - `marine-raw`: Raw downloaded data files.
   - `marine-curated`: Cleaned and standardized datasets.
   - `marine-derived`: Processed model outputs and indicators.
   - `marine-media`: Imagery and bathymetric visual assets.
   - `marine-edna`: Environmental DNA sequences and logs.
   - `marine-models`: Machine learning weights and checkpoints.
   - `marine-research`: Exploratory research notebooks and assets.

---

## 5. Python & Backend Setup

### Prerequisites
- Python 3.12+
- Virtual environment (`venv`)

### 1. Set Up Virtual Environment
```bash
cd backend
python -m venv .venv

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# On Linux / macOS:
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `backend/.env`:
```bash
cp .env.example .env
```
Fill in your local passwords:
```env
APP_NAME=Sstrix Marine AI Platform
APP_ENV=development
APP_DEBUG=true

DATABASE_HOST=127.0.0.1
DATABASE_PORT=5432
DATABASE_NAME=sstrix_marine
DATABASE_USER=sstrix_admin
DATABASE_PASSWORD=<your-local-db-password>

SEAWEEDFS_ENDPOINT=http://127.0.0.1:8333
SEAWEEDFS_ACCESS_KEY=<your-access-key>
SEAWEEDFS_SECRET_KEY=<your-secret-key>
```

---

## 6. Running the Application

From the `backend` directory (with virtual environment activated):

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### API Documentation & Endpoints
- **Interactive Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc UI**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Root**: `GET http://127.0.0.1:8000/`
- **Health Check**: `GET http://127.0.0.1:8000/health` (checks PostgreSQL and SeaweedFS)
- **Copernicus Search**: `GET http://127.0.0.1:8000/api/v1/data-sources/copernicus/search?keyword=salinity&limit=10`

---

## 7. Current Implementation Status

### Verified and Implemented
- **FastAPI Core Architecture**: Modular application structure, settings configuration, and health endpoints.
- **PostgreSQL / PostGIS Engine**: Connection pooling, connection test, session management.
- **SeaweedFS S3 Integration**: Boto3 client, bucket listing health check, bucket provisioning (`create_buckets.py`), and read/write storage tests (`storage_test.py`).
- **Copernicus Marine Catalogue Discovery**:
  - Direct integration via `copernicusmarine.describe()`.
  - Endpoint: `GET /api/v1/data-sources/copernicus/search`.
  - Supports keyword queries (e.g., `thetao`, `salinity`, `chlorophyll`).
  - *Note: This provides catalogue product discovery and metadata exploration. Ingestion and extraction of raw measurement data arrays are scheduled for subsequent pipeline milestones.*

### In Progress / Upcoming (Dedicated Branches)
- **NOAA & Argo Connectors** (`feature/noaa-argo-connectors`):
  - ERDDAP / NODC API client research and connector implementation.
  - Argo float data access, profile metadata queries, and common response normalization.
- **INCOIS Integration & Data Validation** (`feature/incois-validation`):
  - INCOIS web service integration and Indian Ocean observation retrieval.
  - Marine data quality indicators, provenance tracking, and spatial validation.

---

## 8. Running Tests

Run the test suite from the `backend/` directory:

```bash
cd backend
python -m unittest discover tests
```

To run individual tests:
```bash
python -m unittest tests/test_api.py
```

To verify local S3 storage connectivity:
```bash
python storage_test.py
```

---

## 9. Team Contribution Workflow

Please refer to [CONTRIBUTING.md](CONTRIBUTING.md) for full branch management rules, pull request requirements, and security practices.
