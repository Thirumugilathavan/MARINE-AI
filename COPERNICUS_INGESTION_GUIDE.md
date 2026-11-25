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
* **Vertical Range**: 50 depth levels from surface (0.5m) to ocean floor (5728m)
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
        depth_bounds={"min_depth": 0.5, "max_depth": 5728.0},
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
* **`ingestion_jobs`**: Tracks the ingestion job lifecycle (`pending`, `running`, `completed`, `failed`), requested parameters, and error messages.
* **`ingestion_assets`**: Stores details of the downloaded NetCDF asset, including file name, staging path, file size in bytes, SHA-256 hash, and optional S3 URI.
* **`validation_reports`**: Stores the output of the `NetCDFValidator`, including CF compliance, dimensions, coordinate bounds, warnings, errors, and variable summary statistics (JSON).
* **`provenance_records`**: Captures complete audit lineage: source provider, product ID, dataset ID, query parameters, timestamp, tool version, and asset SHA-256 hash.

---

## 7. Storage Policy

1. **Local Staging (Default)**:
   * Downloaded NetCDF files are placed in `dataset-staging/copernicus-downloads/`.
   * Fast, direct local filesystem access for data processing, xarray analysis, and model feeding.
2. **SeaweedFS S3 Archival (Optional)**:
   * When SeaweedFS is active and configured in `.env`, assets can be archived into the `marine-raw` bucket:
     `s3://marine-raw/copernicus/GLOBAL_ANALYSISFORECAST_PHY_001_024/{job_id}/{filename}.nc`
   * The local staging file remains preserved.

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
    "minimum_longitude": 88.0,
    "maximum_longitude": 88.2,
    "minimum_latitude": 15.0,
    "maximum_latitude": 15.2,
    "minimum_depth": 0.5,
    "maximum_depth": 1.0,
    "start_datetime": "2024-01-01T00:00:00Z",
    "end_datetime": "2024-01-01T23:59:59Z"
  }'
```

**Response**:
```json
{
  "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
  "estimated_size_mb": 0.013,
  "estimated_total_points": 9,
  "bounding_box_area_deg2": 0.04,
  "duration_days": 1.0,
  "status": "valid",
  "message": "Preview valid. The request was run with the dry-run option."
}
```

### 4. Create Ingestion Job (Asynchronous Background Task)
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/data-sources/copernicus/ingestions?background=true" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
    "variables": ["thetao"],
    "minimum_longitude": 88.0,
    "maximum_longitude": 88.2,
    "minimum_latitude": 15.0,
    "maximum_latitude": 15.2,
    "minimum_depth": 0.5,
    "maximum_depth": 1.0,
    "start_datetime": "2024-01-01T00:00:00Z",
    "end_datetime": "2024-01-01T23:59:59Z",
    "output_filename": "bay_of_bengal_thetao_sample.nc"
  }'
```

**Response**:
```json
{
  "job_id": "9b1d3d6e-8260-449e-ba73-514be0c27258",
  "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
  "status": "pending",
  "created_at": "2026-11-25T04:45:00Z",
  "message": "Ingestion job queued as background task"
}
```

### 5. Check Ingestion Status & Validation
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/data-sources/copernicus/ingestions/9b1d3d6e-8260-449e-ba73-514be0c27258"
```

### 6. Search Copernicus Catalogue (Preserved)
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

## 10. Operational Considerations & Limitations

1. **Copernicus Service Outages**: The Copernicus Marine API may occasionally experience maintenance or throttling. The service catches connection errors and flags the job status as `failed` with diagnostic details.
2. **Bounding Box Size**: Requests exceeding 2,500 deg² or 365 days are rejected to protect server memory and storage.
3. **Coordinate Orientations**: Longitudes and latitudes must satisfy `minimum <= maximum`. Cross-antimeridian queries (e.g., 170° to -170°) should be split into two queries if required.
4. **Data Immutability**: All downloaded assets have computed SHA-256 hashes recorded at ingestion time to guarantee provenance and detect tampering.
