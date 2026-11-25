# Copernicus Marine NRT and Historical Ingestion Specification

This document provides technical documentation for the Copernicus Marine Service Near-Real-Time (NRT) and Historical Data Ingestion Pipeline implemented in the **MARINE-AI Platform**.

---

## 1. Verified Copernicus Dataset Identifiers

All candidate dataset identifiers below have been verified against the live Copernicus Marine Data Store (`copernicusmarine` 2.5.1 / STAC metadata endpoint):

| Cadence | Variable(s) | Dataset Identifier | Product Identifier | Resolution | Cadence Label |
|---|---|---|---|---|---|
| **NRT 6-Hourly** | `thetao` | `cmems_mod_glo_phy-thetao_anfc_0.083deg_PT6H-i` | `GLOBAL_ANALYSISFORECAST_PHY_001_024` | 0.083° (~1/12°) | 6-hourly instantaneous |
| **NRT 6-Hourly** | `so` | `cmems_mod_glo_phy-so_anfc_0.083deg_PT6H-i` | `GLOBAL_ANALYSISFORECAST_PHY_001_024` | 0.083° (~1/12°) | 6-hourly instantaneous |
| **NRT 6-Hourly** | `uo`, `vo` | `cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i` | `GLOBAL_ANALYSISFORECAST_PHY_001_024` | 0.083° (~1/12°) | 6-hourly instantaneous |
| **NRT Daily** | `thetao` | `cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m` | `GLOBAL_ANALYSISFORECAST_PHY_001_024` | 0.083° (~1/12°) | Daily mean |
| **NRT Daily** | `so` | `cmems_mod_glo_phy-so_anfc_0.083deg_P1D-m` | `GLOBAL_ANALYSISFORECAST_PHY_001_024` | 0.083° (~1/12°) | Daily mean |
| **NRT Daily** | `uo`, `vo` | `cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m` | `GLOBAL_ANALYSISFORECAST_PHY_001_024` | 0.083° (~1/12°) | Daily mean |
| **Historical Daily** | `thetao`, `so`, `uo`, `vo` | `cmems_mod_glo_phy_my_0.083deg_P1D-m` | `GLOBAL_MULTIYEAR_PHY_001_030` | 0.083° (~1/12°) | Multi-year daily reanalysis |

---

## 2. Supported Oceanographic Variables

| Variable | Standard Name | Units | Physical Validation Range | Description |
|---|---|---|---|---|
| `thetao` | `sea_water_potential_temperature` | `degrees_C` | -3.0 °C to 45.0 °C | Potential temperature of seawater |
| `so` | `sea_water_salinity` | `1e-3` (psu) | 0.0 to 50.0 psu | Practical salinity of seawater |
| `uo` | `eastward_sea_water_velocity` | `m s-1` | -15.0 to 15.0 m/s | Zonal ocean current velocity |
| `vo` | `northward_sea_water_velocity` | `m s-1` | -15.0 to 15.0 m/s | Meridional ocean current velocity |

---

## 3. Spatial Extent: Indian Ocean Bounding Box

To ensure bounded downloads and prevent accidental requests for global multi-gigabyte grids, all retrievals enforce strict bounding:

- **Western Longitude**: `30.0°E`
- **Eastern Longitude**: `120.0°E`
- **Southern Latitude**: `-30.0°S`
- **Northern Latitude**: `30.0°N`

Bounds are configurable per ingestion request, with Indian Ocean defaults. Requests with inverted coordinates or out-of-range bounds are rejected before contacting external providers.

---

## 4. Ingestion Pipeline Architecture

```
+------------------------------------------------------------------------+
|                          Ingestion Request                             |
|        (Cadence, Variables, Bounding Box, Date Range, Depth)           |
+-----------------------------------+------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                         Validation Gate                                |
|  - Validate Cadence (nrt_six_hourly / nrt_daily / historical_daily)    |
|  - Validate Variables (thetao, so, uo, vo)                             |
|  - Validate Coordinate Range & Ordering                                |
+-----------------------------------+------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                       Copernicus Marine Subset                         |
|  - Plan minimal dataset requests                                       |
|  - Enforce spatial subset: [min_lon, min_lat, max_lon, max_lat]        |
|  - Enforce temporal and depth window                                   |
|  - copernicusmarine.subset() with credentials                          |
+-----------------------------------+------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                 Normalization & Physical Validation                    |
|  - Inspect dimensions & coordinate arrays                              |
|  - Physical sanity checks (out-of-bounds, NaN / land mask metrics)     |
|  - Compute SHA-256 checksum                                            |
+-----------------------------------+------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                     Bounded Storage & Provenance                       |
|  - Upload raw subset to SeaweedFS S3 (bucket: marine-raw)              |
|  - Key: copernicus/{cadence}/{dataset_id}/{ingestion_id}/{filename}    |
|  - Save provenance JSON with audit metadata & validation metrics       |
+------------------------------------------------------------------------+
```

---

## 5. API Endpoints

### 1. `GET /api/v1/data-sources/copernicus/datasets`
Returns metadata on all verified Copernicus datasets, supported variables, cadences, and default spatial parameters.

### 2. `GET /api/v1/data-sources/copernicus/region`
Returns the default Indian Ocean bounding box coordinates and resolution.

### 3. `POST /api/v1/data-sources/copernicus/validate`
Validates bounding box, cadence, and variable parameters prior to triggering an ingestion run.

### 4. `POST /api/v1/data-sources/copernicus/ingest`
Triggers the end-to-end ingestion pipeline:
```json
{
  "cadence": "nrt_daily",
  "variables": ["thetao", "so", "uo", "vo"],
  "minimum_longitude": 30.0,
  "maximum_longitude": 120.0,
  "minimum_latitude": -30.0,
  "maximum_latitude": 30.0,
  "start_datetime": "2024-01-01T00:00:00",
  "end_datetime": "2024-01-02T00:00:00",
  "minimum_depth": 0.0,
  "maximum_depth": 10.0,
  "dry_run": false
}
```

---

## 6. Authentication & Configuration

Copernicus Marine Data Store requires free user credentials for downloading or subsetting data:

1. Register for free at: [https://data.marine.copernicus.eu/register](https://data.marine.copernicus.eu/register)
2. Add your credentials to `backend/.env`:
   ```env
   COPERNICUS_MARINE_USERNAME=your_username
   COPERNICUS_MARINE_PASSWORD=your_password
   ```
3. When credentials are not provided, the pipeline gracefully returns an `authentication_required` response, preventing unauthenticated process hangs.

---

## 7. Operational Limitations & Considerations

1. **Authentication Requirement**: While catalogue search and metadata queries do not require authentication, data subsetting and download strictly require Copernicus Marine credentials.
2. **Network Rate Limits**: Live subset requests depend on Copernicus Marine Data Store availability and network throughput.
3. **Time Window Slicing**: For multi-month or multi-year ingestion tasks, requests should be sliced into discrete daily or monthly chunks to manage memory and file sizes.
