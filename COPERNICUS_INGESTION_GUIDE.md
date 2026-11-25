# Copernicus Marine Data Ingestion Guide

This document details the architecture, configuration, workflows, validation rules, database persistence, and operational guidelines for the Copernicus Marine data ingestion pipeline within the **MARINE-AI Platform**.

---

## 1. Architecture Overview

The Copernicus Marine Ingestion Pipeline is implemented as a production-grade, modular service integrated directly into the FastAPI application. It follows a bounded, validated, and provenanced approach to acquiring marine environmental datasets.

```
+-----------------------------------------------------------------------------------+
|                            FastAPI REST API Layer                                 |
|                                                                                   |
|  GET /datasets         GET /datasets/{id}        POST /preview                    |
|  POST /ingestions      GET /ingestions           GET /ingestions/{id}             |
|  POST /ingestions/{id}/validate                  GET /search (Catalogue)          |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                               CopernicusService                                   |
|                        (Orchestration & Job Lifecycle)                            |
+-----------------------------------------+-----------------------------------------+
                    |                                         |
                    v                                         v
+---------------------------------------+ +-----------------------------------------+
|      CopernicusRetrievalService       | |             NetCDFValidator             |
| - Parameter & Coordinate Validation   | | - File format & CF-1.8 conventions      |
| - Area & Temporal Window Limits       | | - Dimension & Coordinate verification   |
| - Dry-run Estimation via Subset API   | | - Missing value (NaN) ratios            |
| - Bounded NetCDF Download & Staging   | | - Physical range checks & statistics    |
+-------------------+-------------------+ +--------------------+--------------------+
                    |                                          |
                    v                                          v
+---------------------------------------+ +-----------------------------------------+
|         Storage Layer                 | |            Database Models              |
| - Local Staging: dataset-staging/     | | - dataset_registry                      |
| - S3 / SeaweedFS: marine-raw bucket   | | - ingestion_jobs                        |
| - SHA-256 Checksums & Provenance      | | - ingestion_assets                      |
|                                       | | - validation_reports                    |
|                                       | | - provenance_records                    |
+---------------------------------------+ +-----------------------------------------+
```

---

## 2. Verified Dataset Registry

The ingestion module uses an extensible dataset registry (`DATASET_REGISTRY`) that maintains rigorous metadata for each verified Copernicus product and dataset.

### Primary Verified Product & Dataset

* **Product ID**: `GLOBAL_ANALYSISFORECAST_PHY_001_024`
* **Product Title**: Global Ocean Physics Analysis and Forecast
* **Dataset ID**: `cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m`
* **Dataset Description**: Daily mean 3D ocean potential temperature on a 0.083° (~9 km) global grid with 50 standard depth levels.
* **Update Frequency**: Daily
* **Horizontal Resolution**: 0.083° x 0.083° (~9 km)
* **Vertical Range**: 50 depth levels from surface (0.494m) to ocean floor (5728m)
* **Primary Variable**:
  * **Variable Name**: `thetao`
  * **Standard Name**: `sea_water_potential_temperature`
  * **Units**: `degrees_C`
  * **Physical Valid Range**: `[-4.0, 40.0] °C`

### Extension Mechanism

Additional oceanographic variables and datasets (such as salinity `so`, eastward velocity `uo`, northward velocity `vo`, 6-hourly NRT, or historical reanalysis) can be added safely using the `register()` method:

```python
from app.modules.data_sources.copernicus.dataset_registry import (
    DATASET_REGISTRY,
    RegisteredDataset,
)

DATASET_REGISTRY.register(
    RegisteredDataset(
        dataset_id="cmems_mod_glo_phy-so_anfc_0.083deg_P1D-m",
        product_id="GLOBAL_ANALYSISFORECAST_PHY_001_024",
        title="Global Ocean Salinity Analysis and Forecast (Daily)",
        description="Daily mean sea water salinity on a 0.083 degree grid",
        supported_variables=["so"],
        variable_metadata={
            "so": {
                "standard_name": "sea_water_salinity",
                "units": "0.001",
                "valid_min": 0.0,
                "valid_max": 50.0,
            }
        },
        spatial_bounds={"min_lon": -180.0, "max_lon": 180.0, "min_lat": -90.0, "max_lat": 90.0},
        depth_bounds={"min_depth": 0.494, "max_depth": 5728.0},
        time_resolution="daily",
        is_verified=True,
    )
)
```

---

## 3. Copernicus Marine Authentication

Authentication is handled securely via the Copernicus Marine Python Toolbox (`copernicusmarine` 2.5.1).

### Setup Instructions
1. Obtain an account at [marine.copernicus.eu](https://marine.copernicus.eu).
2. On your local machine, run:
   ```bash
   copernicusmarine login
   ```
3. Enter your Copernicus Marine username and password when prompted.
4. The client securely stores authentication tokens in your local user directory:
   * **Windows**: `C:\Users\<username>\.copernicusmarine\.copernicusmarine-credentials`
   * **Linux/macOS**: `~/.copernicusmarine/.copernicusmarine-credentials`

### Security Guarantees
* **No hardcoded credentials**: The platform never stores passwords or tokens in code, `.env` files, or configuration templates.
* **No secret logging**: The service suppresses and filters sensitive tokens from debug logs, test outputs, and error messages.
* **Environment independence**: When no explicit credentials are passed in API requests, the client automatically defaults to the system credentials cache.

---

## 4. Safety Constraints & Retrieval Bounds

To prevent accidental downloads of terabyte-scale global NetCDF grids, all ingestion requests are strictly validated against geographic, temporal, and spatial bounds:

| Parameter | Allowed Range / Constraint | Description |
|---|---|---|
| **Longitude** | `[-180.0, 180.0]` and `min_lon <= max_lon` | Target bounds (Indian Ocean default: 30°E to 120°E) |
| **Latitude** | `[-90.0, 90.0]` and `min_lat <= max_lat` | Target bounds (Indian Ocean default: -30°S to 30°N) |
| **Depth** | `[0.0, 6000.0] meters` | Standard ocean depth levels |
| **Area Limit** | `<= 2,500 deg²` | `(max_lon - min_lon) * (max_lat - min_lat) <= 2500` |
| **Time Window** | `<= 365 days` | Maximum retrieval duration per job |
| **File Safety** | Basename only | Path traversal patterns (`../`, `..\\`) are stripped |

---

## 5. NetCDF Validation Module

Every downloaded or staged NetCDF file is processed through `NetCDFValidator` (using `xarray` and `numpy`) before being marked as completed.

### Checks Performed
1. **File Integrity**: Verifies the file exists, is non-empty, and can be opened by the NetCDF engine.
2. **CF Conventions**: Checks for CF-compliance attributes (e.g., `Conventions = "CF-1.8"`).
3. **Dimensions & Coordinates**: Verifies the presence of required coordinate dimensions (`time`, `depth`, `latitude`, `longitude`).
4. **Coordinate Bounds**: Checks whether coordinates in the file align with the requested bounding box within numerical tolerances.
5. **Variable Presence**: Verifies all requested data variables (e.g., `thetao`) exist in the file.
6. **Data Completeness & NaN Ratios**: Counts total, valid, and missing data points (accounting for land masks).
7. **Physical Bounds**: Validates that temperature values fall within physically realistic ranges (e.g., -4.0 °C to 40.0 °C). Values outside this range trigger validation warnings.
8. **Summary Statistics**: Computes min, max, mean, and standard deviation for each variable.

---

## 6. Database Schema & Persistence

The ingestion service uses five relational tables managed via SQLAlchemy 2.0 (compatible with PostgreSQL/PostGIS and SQLite for tests):

```
+---------------------+       1:N       +---------------------+
|   dataset_registry  |---------------->|   ingestion_jobs    |
+---------------------+                 +---------------------+
                                                   | 1:1
                                                   v
+---------------------+       1:1       +---------------------+
| validation_reports  |<----------------|  ingestion_assets   |
+---------------------+                 +---------------------+
           ^                                       | 1:1
           |                   1:1                 v
           +----------------------------+---------------------+
                                        | provenance_records  |
                                        +---------------------+
```

### Table Descriptions
* **`dataset_registry`**: Catalogs supported datasets, product IDs, verified variables, and valid ranges.
* **`ingestion_jobs`**: Tracks the ingestion job lifecycle (`pending`, `downloading`, `validating_data`, `completed`, `failed`), requested parameters, and error messages.
* **`ingestion_assets`**: Stores details of the downloaded NetCDF asset, including file name, staging path, file size in bytes (`BigInteger`), SHA-256 hash, and optional S3 URI.
* **`validation_reports`**: Stores the output of the `NetCDFValidator`, including CF compliance, dimensions, coordinate bounds, warnings, errors, and variable summary statistics (JSON/JSONB).
* **`provenance_records`**: Captures complete audit lineage: source provider, product ID, dataset ID, query parameters, timestamp, tool version, and asset SHA-256 hash.

---

## 7. Storage Policy

1. **Local Staging (Default - API-first policy)**:
   * Downloaded NetCDF files are placed in `dataset-staging/copernicus-downloads/`.
   * Copernicus data that remains accessible through its upstream API is **not** duplicated into object storage by default.
   * Fast, direct local filesystem access for data processing, xarray analysis, and model feeding.
2. **SeaweedFS S3 Archival (Optional - `retain_in_s3 = True`)**:
   * When permanent object archival is explicitly requested, assets are uploaded to SeaweedFS S3 in bucket `marine-raw`:
     `s3://marine-raw/copernicus/{dataset_id}/{job_id}/{filename}.nc`
   * The database asset record records `storage_backend = "seaweedfs_s3"`, `storage_bucket = "marine-raw"`, and `storage_key`.
   * The local staging copy remains preserved for local cache and immediate fast validation.

---

## 8. API Reference & Examples

### 1. List Registered Datasets
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/data-sources/copernicus/datasets"
```

### 2. Get Dataset Details
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/data-sources/copernicus/datasets/cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m"
```

### 3. Dry-Run / Preview Request
Evaluate estimated download size and parameter validity without downloading:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/data-sources/copernicus/preview" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
    "variables": ["thetao"],
    "minimum_longitude": 85.0,
    "maximum_longitude": 85.2,
    "minimum_latitude": 12.0,
    "maximum_latitude": 12.2,
    "minimum_depth": 0.494,
    "maximum_depth": 0.495,
    "start_datetime": "2026-11-20T00:00:00Z",
    "end_datetime": "2026-11-20T23:59:59Z"
  }'
```

**Response**:
```json
{
  "request_id": "9b1d3d6e-8260-449e-ba73-514be0c27258",
  "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
  "product_id": "GLOBAL_ANALYSISFORECAST_PHY_001_024",
  "product_title": "Global Ocean Physics Analysis and Forecast",
  "estimated_file_size_mb": 0.0131,
  "estimated_data_transfer_mb": 0.0131,
  "dry_run_status": "success",
  "dry_run_message": "StatusMessage.DRY_RUN",
  "selected_extent": {
    "longitude": {"min": 85.0, "max": 85.1667, "unit": "degrees_east"},
    "latitude": {"min": 12.0, "max": 12.1667, "unit": "degrees_north"},
    "time": {"min": "2026-11-20T00:00:00+00:00", "max": "2026-11-20T00:00:00+00:00", "unit": "iso8601"},
    "depth": {"min": 0.494, "max": 0.494, "unit": "m"}
  }
}
```

### 4. Create Ingestion Job (Asynchronous Background Task)
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/data-sources/copernicus/ingestions" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
    "variables": ["thetao"],
    "minimum_longitude": 85.0,
    "maximum_longitude": 85.2,
    "minimum_latitude": 12.0,
    "maximum_latitude": 12.2,
    "minimum_depth": 0.494,
    "maximum_depth": 0.495,
    "start_datetime": "2026-11-20T00:00:00Z",
    "end_datetime": "2026-11-20T23:59:59Z",
    "output_filename": "bay_of_bengal_thetao_sample.nc",
    "retain_in_s3": false
  }'
```

**Response**:
```json
{
  "job_id": "fd1db592-8735-4e35-a584-8a3917091d24",
  "status": "queued",
  "message": "Ingestion job submitted successfully."
}
```

### 5. Check Ingestion Status & Validation
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/data-sources/copernicus/ingestions/fd1db592-8735-4e35-a584-8a3917091d24"
```

### 6. Synchronous Ingestion (for tests & small requests)
Append query parameter `?run_synchronously=true`:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/data-sources/copernicus/ingestions?run_synchronously=true" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
    "variables": ["thetao"],
    "minimum_longitude": 85.0,
    "maximum_longitude": 85.2,
    "minimum_latitude": 12.0,
    "maximum_latitude": 12.2,
    "minimum_depth": 0.494,
    "maximum_depth": 0.495,
    "start_datetime": "2026-11-20T00:00:00Z",
    "end_datetime": "2026-11-20T23:59:59Z"
  }'
```

### 7. Search Copernicus Catalogue (Preserved)
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/data-sources/copernicus/search?keyword=thetao&limit=5"
```

---

## 9. Running Automated Tests

The test suite validates dataset registry lookups, safety constraints, dry-run previews, NetCDF validation against real fixtures, API endpoints, and database models.

Run the full test suite from the `backend/` directory:

```bash
cd backend
python -m unittest discover -v tests
```

### Included Test Suites
* `tests/test_dataset_registry.py`: Registry registration, variable lookups, and validation checks.
* `tests/test_retrieval.py`: Retrieval parameter validation, bounding box limits, filename sanitization, dry-run preview, and mocked downloads.
* `tests/test_netcdf_validation.py`: Validation rules, CF conventions, missing values, physical bounds checks, and integration with the verified Indian Ocean test fixture (`dataset-staging/copernicus-test/bay_of_bengal_thetao_test.nc`).
* `tests/test_copernicus_api.py`: FastAPI endpoints for dataset listing, preview, synchronous and asynchronous ingestion, job status, and error handling.
* `tests/test_database.py`: SQLAlchemy database models and relationship persistence lifecycle.
* `tests/test_api.py`: Health checks and catalogue discovery endpoints.

---

## 10. Local Setup & Troubleshooting

### Infrastructure Setup
The pipeline connects to:
- **PostgreSQL 17 with PostGIS 3.5**: Container `sstrix-postgres` on `127.0.0.1:5432`
- **SeaweedFS S3 Object Store**: Container `sstrix-seaweedfs` on `127.0.0.1:8333`

If containers are stopped:
```bash
docker start sstrix-postgres
docker start sstrix-seaweedfs
```

### Common Issues & Remedies
1. **Authentication Error / Missing Credentials**:
   * Run `copernicusmarine login` once to store credentials in `~/.copernicusmarine/`.
2. **Connection Timed Out to Copernicus**:
   * Verify your internet connection. Upstream Copernicus API maintenance is reported with HTTP 502.
3. **Database Disconnected**:
   * Check container status with `docker ps`. Verify port 5432 is bound to `127.0.0.1`.
4. **S3 Connection Refused**:
   * Verify container `sstrix-seaweedfs` is running and port 8333 is open.
5. **Bounding Box Error**:
   * Ensure `minimum_longitude <= maximum_longitude` and `minimum_latitude <= maximum_latitude`.
   * Keep bounding box area below `2,500 deg²`.
