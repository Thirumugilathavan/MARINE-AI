# UNIFIED MARINE DATA INGESTION GUIDE
## Multi-Provider Oceanographic Architecture (Copernicus, NOAA, Argo, INCOIS)

---

## 1. Executive Summary & Architecture Overview

The **MARINE-AI Platform** provides a high-throughput, scientifically validated multi-provider marine data ingestion pipeline. It generalizes the single-source Copernicus pipeline into an extensible provider-agnostic framework capable of discovering, previewing, retrieving, validating, and persisting heterogeneous marine datasets:
- **Satellite Observations**: Gridded Sea Surface Temperature (NOAA OISST) & Ocean Surface Winds (INCOIS ASCAT).
- **In-Situ Vertical Profiles**: Global autonomous profiling floats (Euro-Argo / Coriolis GDAC).
- **Numerical Ocean Forecasts & Reanalysis**: Global 3D physical ocean models (Copernicus Marine Service).

### Core Architectural Components

```
+----------------------------------------------------------------------------------------------------+
|                                    Unified API Layer (FastAPI)                                     |
|                                                                                                    |
|    /api/v1/providers/*           /api/v1/ingestions/*           /api/v1/data-sources/copernicus/*  |
|    (Discovery, Preview, Ingest)   (Job State, Assets, Provenance)   (Preserved Legacy Endpoints)   |
+--------------------------------------------------+-------------------------------------------------+
                                                   |
                                                   v
+----------------------------------------------------------------------------------------------------+
|                                   Unified Ingestion Orchestrator                                   |
|  - Parameter Validation     - SHA-256 Hash Generation      - Scientific CF-1.8 Validation          |
|  - Dry-Run Size Estimator   - SeaweedFS S3 Persistence     - Provenance & Citation Lineage         |
+--------------------------------------------------+-------------------------------------------------+
                                                   |
                                                   v
+----------------------------------------------------------------------------------------------------+
|                             Provider Registry (BaseMarineProvider ABC)                             |
|  +--------------------+  +--------------------+  +--------------------+  +--------------------+    |
|  |     Copernicus     |  |       NOAA         |  |        Argo        |  |       INCOIS       |    |
|  |  (CopernicusToolbox|  |   (CoastWatch      |  |    (Euro-Argo      |  |   (MoES ERDDAP     |    |
|  |     Subset API)    |  |  Griddap REST)     |  |  Tabledap REST)    |  |   Griddap REST)    |    |
|  +--------------------+  +--------------------+  +--------------------+  +--------------------+    |
+--------------------------------------------------+-------------------------------------------------+
                          |                                                  |
                          v                                                  v
+--------------------------------------------------+  +----------------------------------------------+
|             PostgreSQL 17 / PostGIS              |  |         SeaweedFS S3 Storage Buckets         |
|  - data_providers         - validation_reports   |  |  - marine-raw (persisted NetCDF assets)      |
|  - dataset_registry       - provenance_records   |  |  - marine-curated, marine-derived, etc.      |
|  - ingestion_jobs         - ingestion_assets     |  |                                              |
+--------------------------------------------------+  +----------------------------------------------+
```

---

## 2. Integrated Marine Data Providers

| Provider ID | Provider Name | Organization | Access Protocol | Auth Required | Rate Limits & Fair Use |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `copernicus` | Copernicus Marine Service | Mercator Ocean International / EC | `copernicusmarine_toolbox` | **Yes** (CLI token) | Max 2500 deg² area / request |
| `noaa` | National Oceanic & Atmospheric Administration | NOAA CoastWatch / NCEI | `erddap_griddap_rest` | **No** (Public domain) | Max 1 req/sec recommended |
| `argo` | International Argo Program / Euro-Argo | Euro-Argo ERIC / Coriolis GDAC | `erddap_tabledap` | **No** (CC-BY 4.0) | < 10 concurrent requests |
| `incois` | Indian National Centre for Ocean Info Services | Ministry of Earth Sciences, Govt of India | `erddap_griddap` | **No** (Open Data Policy) | Institutional fair use |

---

## 3. Verified Datasets & Scientific Parameters

### 3.1. NOAA CoastWatch ERDDAP
- **Dataset ID**: `ncdcOisst21Agg_LonPM180`
- **Product Title**: NOAA 1/4° Daily Optimum Interpolation Sea Surface Temperature (OISST) v2.1
- **Temporal Resolution**: Daily
- **Spatial Resolution**: 0.25° grid (~27 km)
- **Supported Variables**:
  - `sst`: Daily Sea Surface Temperature (°C, valid range: -3.0 to 45.0 °C)
  - `anom`: Sea Surface Temperature Anomaly (°C, valid range: -15.0 to 15.0 °C)
  - `err`: Estimated Error of Daily SST (°C, valid range: 0.0 to 10.0 °C)
  - `ice`: Sea Ice Concentration (fraction, valid range: 0.0 to 1.0)
- **Coverage**: Global [-180, 180] lon, [-90, 90] lat; from 1981-09-01 to present.

### 3.2. Argo Global In-Situ Profiling Floats
- **Dataset ID**: `ArgoFloats`
- **Product Title**: Argo Global In-Situ Profiling Floats Dataset (Euro-Argo / Coriolis GDAC)
- **Data Type**: `in_situ_profile` (vertical profile trajectories)
- **Supported Variables**:
  - `temp`: In-situ Seawater Temperature (°C, valid range: -2.5 to 40.0 °C)
  - `psal`: Practical Salinity (PSU, valid range: 2.0 to 42.0 PSU)
  - `pres`: Pressure / Depth Equivalent (dbar, valid range: 0.0 to 6500.0 dbar)
  - `temp_qc`, `psal_qc`, `pres_qc`: Quality control flags (1=good, 2=probably good, 3=bad, 4=bad, 9=missing)
  - `platform_number`: WMO float identifier number
  - `cycle_number`: Profile cycle counter
  - `data_mode`: Processing mode (`R` = Real-time, `A` = Adjusted, `D` = Delayed-mode)
- **Coverage**: Global oceans; 1999-01-01 to present.

### 3.3. INCOIS Indian Ocean Operational Products
- **Dataset ID**: `ascat_daily_datasets`
- **Product Title**: INCOIS ASCAT Daily Surface Wind Speed and Stress Product
- **Temporal Resolution**: Daily (2007-03-21 to 2023-05-21)
- **Spatial Resolution**: 0.25° grid
- **Supported Variables**:
  - `wind_speed`: Ocean Surface Wind Speed at 10m height (m/s, valid range: 0.0 to 75.0 m/s)
  - `wind_stress`: Downward wind stress magnitude (N/m², valid range: 0.0 to 5.0 N/m²)
  - `zonal_wind_stress`: Eastward wind stress component (N/m², valid range: -5.0 to 5.0 N/m²)
  - `meridional_wind_stress`: Northward wind stress component (N/m², valid range: -5.0 to 5.0 N/m²)
- **Coverage**: Indian Ocean / Tropical domain [30, 120] lon, [-40, 40] lat.

### 3.4. Copernicus Marine Service (CMEMS)
- **Dataset ID**: `cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m`
- **Product Title**: Global Ocean Physics Analysis and Forecast (PHY_001_024)
- **Supported Variables**: `thetao` (Potential temperature in °C), `so` (Salinity in PSU), `uo` (Eastward velocity in m/s), `vo` (Northward velocity in m/s).

---

## 4. Key Technical Challenges & Engineering Solutions

### 4.1. INCOIS Tomcat RFC 7230 Bracket URI Encoding
- **Problem**: The INCOIS ERDDAP service runs behind Apache Tomcat which strictly enforces RFC 7230 and rejects unencoded brackets `[` and `]` with `HTTP 400 - Invalid character found in the request target`.
- **Solution**: The `INCOISMarineProvider` explicitly encodes constraint brackets (`[` -> `%5B`, `]` -> `%5D`, `(` -> `%28`, `)` -> `%29`) in the griddap query string.
- **Dimensionality**: In addition, `ascat_daily_datasets` is a 4D grid `(time, depth, latitude, longitude)` where the depth coordinate is fixed at `10.0m` (standard anemometer level). The query generator injects `[(10.0)]` to satisfy the dimensional hierarchy.

### 4.2. NetCDF-3 vs. NetCDF-4 IO Drivers
- **Problem**: Python's `xarray` default install with `h5netcdf` only opens NetCDF-4/HDF5 formats. ERDDAP services stream NetCDF-3 classic format, triggering `ValueError: found the following matches with the input file in xarray's IO backends: ['netcdf4', 'scipy']. But their dependencies may not be installed`.
- **Solution**: Integrated `netCDF4` (`1.7.5.1.post1`) and `cftime` (`1.6.6.1`) into the backend virtual environment and `requirements.txt`.

### 4.3. Argo Tabledap Coordinate & QC Indexing
- **Problem**: Tabledap returns tabular in-situ profiles with a 1D `row` dimension rather than regular rectilinear grids. Quality control flags must be checked independently per profile point.
- **Solution**: The `ArgoMarineProvider.validate_data` unpacks 1D arrays along `row`, checks physical limits for temperature, salinity, and pressure, tallies QC flag distributions (`flag_1` through `flag_9`), and summarizes data modes (`R`, `A`, `D`).

### 4.4. SSL Verification for Government Portals
- **Problem**: Indian Government portals (`.gov.in`) often utilize root certificates issued by the Controller of Certifying Authorities (CCA) India, causing standard Python `certifi` bundles to report `[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate`.
- **Solution**: The `INCOISMarineProvider` includes configurable SSL trust verification (`verify_ssl=False` default for development, or a path to the custom institutional CA bundle in production).

---

## 5. Unified API Reference

### 5.1. Provider Endpoints

#### `GET /api/v1/providers`
Returns metadata and operational status for all registered marine data providers.

**Example Response**:
```json
[
  {
    "provider_id": "copernicus",
    "name": "Copernicus Marine Service",
    "access_method": "copernicusmarine_toolbox",
    "authentication_required": true,
    "status": "active"
  },
  {
    "provider_id": "noaa",
    "name": "National Oceanic and Atmospheric Administration",
    "access_method": "erddap_griddap_rest",
    "authentication_required": false,
    "status": "active"
  },
  {
    "provider_id": "argo",
    "name": "International Argo Program / Euro-Argo",
    "access_method": "erddap_tabledap",
    "authentication_required": false,
    "status": "operational"
  },
  {
    "provider_id": "incois",
    "name": "Indian National Centre for Ocean Information Services",
    "access_method": "erddap_griddap",
    "authentication_required": false,
    "status": "operational"
  }
]
```

#### `GET /api/v1/providers/{provider_id}/datasets`
Lists verified datasets registered under the specified provider.

#### `POST /api/v1/providers/{provider_id}/preview`
Executes a dry-run estimation of bounding box area, data points, and payload size.

**Example Request**:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/providers/noaa/preview" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "ncdcOisst21Agg_LonPM180",
    "variables": ["sst"],
    "minimum_longitude": 65.0,
    "maximum_longitude": 75.0,
    "minimum_latitude": 10.0,
    "maximum_latitude": 20.0,
    "start_datetime": "2024-01-01T00:00:00Z",
    "end_datetime": "2024-01-03T00:00:00Z"
  }'
```

#### `POST /api/v1/providers/{provider_id}/ingestions`
Triggers synchronous or background ingestion from the specified provider.

**Example Request**:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/providers/incois/ingestions" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "ascat_daily_datasets",
    "variables": ["wind_speed", "wind_stress"],
    "minimum_longitude": 65.0,
    "maximum_longitude": 70.0,
    "minimum_latitude": 10.0,
    "maximum_latitude": 15.0,
    "start_datetime": "2023-01-01T00:00:00Z",
    "end_datetime": "2023-01-02T00:00:00Z",
    "retain_in_s3": true
  }'
```

### 5.2. Ingestion Tracking Endpoints

- `GET /api/v1/ingestions`: List jobs with filtering by provider, status, limit, offset.
- `GET /api/v1/ingestions/{job_id}`: Full status, timestamps, and error diagnostics.
- `GET /api/v1/ingestions/{job_id}/assets`: Retrieved binary files, file sizes, SHA-256 hashes, and S3 keys.
- `GET /api/v1/ingestions/{job_id}/validation`: Coordinate validity, valid point counts, missing points, and variable min/max/mean/std.
- `GET /api/v1/ingestions/{job_id}/provenance`: Citation, provider DOI, licensing, and processing parameters.

---

## 6. Live Verification Results

The multi-provider architecture was executed end-to-end against live official endpoints (`backend/verify_unified_pipeline.py`):

```json
{
  "NOAA": {
    "status": "VERIFIED_LIVE",
    "job_id": "noaa-job-ab4192aaaa60",
    "dataset_id": "ncdcOisst21Agg_LonPM180",
    "file_size_bytes": 15488,
    "sha256": "b9b68c3c472f5c11191c352c80d793481dc90bc830f098e6b5b9b63254fe355f",
    "validation_status": "passed",
    "storage_backend": "seaweedfs_s3"
  },
  "Argo": {
    "status": "VERIFIED_LIVE",
    "job_id": "argo-job-c8be34cf32e9",
    "dataset_id": "ArgoFloats",
    "file_size_bytes": 27672,
    "sha256": "28b5527f50f7c4ca9df1689aecdd30c1c598fa89575ca51259ee52393894cf5d",
    "validation_status": "passed",
    "storage_backend": "seaweedfs_s3"
  },
  "INCOIS": {
    "status": "VERIFIED_LIVE",
    "job_id": "incois-job-190a2495ae22",
    "dataset_id": "ascat_daily_datasets",
    "file_size_bytes": 19792,
    "sha256": "ed1f16cf2fa7357fa345241844ca498a6446b55ff0603982781ac4e3b369fde9",
    "validation_status": "passed",
    "storage_backend": "seaweedfs_s3"
  },
  "Copernicus": {
    "status": "VERIFIED_REGRESSION_OK",
    "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
    "preview_status": "success",
    "estimated_mb": 1.4346
  }
}
```

---

## 7. Frontend Status

> [!IMPORTANT]
> **Frontend Status**: **NOT STARTED**
> 
> This milestone strictly delivers the backend multi-provider architecture, connectors, validation services, and API endpoints. No user interface, React/Vue components, or frontend web assets have been introduced. The backend APIs are fully prepared for subsequent frontend integration via the OpenAPI 3.1 specification at `/openapi.json` and interactive Swagger docs at `/docs`.
