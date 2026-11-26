# SSTRIX MARINE-AI / SIH25041 — Manual Data Access Register

**Register Date**: November 26, 2026  
**Investigator**: Lead Oceanographic Data Platform Architect  
**Repository**: `https://github.com/Thirumugilathavan/MARINE-AI.git`  
**Active Branch**: `feature/marine-complete-backend-platform`  
**Baseline Git Commit**: `3b057d7`  

---

## 1. Scope & Security Policy

In strict adherence to project guidelines:
1. **No Fabricated Credentials**: The platform never mocks, fakes, or fabricates authorization tokens or credentials.
2. **No Access Bypass**: No Cloudflare bot checks, CAPTCHAs, or authentication gates are defeated or intercepted.
3. **No Integration Blocking**: Unauthenticated public scientific integrations proceed independently without being blocked by these registered dependencies.

This register formally catalogues candidate marine data providers that require manual human action, user registration, organizational approval, or private API tokens.

---

## 2. Token-Gated & Account-Restricted Providers

### 2.1 Global Fishing Watch (GFW) — AIS & Apparent Fishing Activity

| Attribute | Detailed Specification |
| :--- | :--- |
| **Provider / Service** | Global Fishing Watch (GFW) |
| **Official Website** | [https://globalfishingwatch.org](https://globalfishingwatch.org) |
| **Developer Portal** | [https://globalfishingwatch.org/our-apis](https://globalfishingwatch.org/our-apis) |
| **Datasets Provided** | Apparent Fishing Effort (4-D spatio-temporal rasters), Vessel Encounters, Transshipment Events, Port Visits, Carrier-to-Fishing vessel rendezvous. |
| **Authentication Method** | HTTP Bearer Token (`Authorization: Bearer <GFW_API_TOKEN>`). |
| **Config Variable Name** | `GFW_API_TOKEN` in `backend/.env`. |
| **Required Human Action** | 1. Navigate to the GFW developer portal and create an account.<br>2. Agree to the GFW Research / Non-Commercial Terms of Service.<br>3. Generate an API token from your account dashboard.<br>4. Add `GFW_API_TOKEN=<your_token>` to `backend/.env`. |
| **Terms & Licence** | Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0) with non-commercial attribution guidelines. |
| **Integration Blocker** | Public calls to `https://gateway.api.globalfishingwatch.org/v3/*` return `HTTP 401 Unauthorized` without a valid token. |

---

### 2.2 Protected Planet (WDPA) — Marine Protected Areas (MPAs)

| Attribute | Detailed Specification |
| :--- | :--- |
| **Provider / Service** | UNEP-WCMC & IUCN World Database on Protected Areas (WDPA) |
| **Official Website** | [https://www.protectedplanet.net](https://www.protectedplanet.net) |
| **Developer API** | [https://api.protectedplanet.net](https://api.protectedplanet.net) |
| **Datasets Provided** | Global Marine Protected Area (MPA) boundaries, IUCN management categories (Ia, Ib, II, etc.), no-take zone designations, governance types, and reported coverage. |
| **Authentication Method** | API Token query parameter (`?token=<WDPA_API_TOKEN>`). |
| **Config Variable Name** | `WDPA_API_TOKEN` in `backend/.env`. |
| **Required Human Action** | 1. Register for an API access token at [api.protectedplanet.net](https://api.protectedplanet.net).<br>2. Fill in the research purpose statement.<br>3. Copy the personal API token into `backend/.env` under `WDPA_API_TOKEN`. |
| **Terms & Licence** | UNEP-WCMC Data Licence: Free for educational and non-commercial research; redistribution subject to attribution. |
| **Integration Blocker** | The API endpoint `https://api.protectedplanet.net/v3/marine_protected_areas` requires an active token; unauthenticated requests receive `HTTP 401 Unauthorized`. |

---

### 2.3 Ocean Networks Canada (ONC) — Oceans 3.0 Real-Time Sensor Network

| Attribute | Detailed Specification |
| :--- | :--- |
| **Provider / Service** | Ocean Networks Canada (ONC) Oceans 3.0 API |
| **Official Website** | [https://www.oceannetworks.ca](https://www.oceannetworks.ca) |
| **Developer Portal** | [https://data.oceannetworks.ca/OpenAPI](https://data.oceannetworks.ca/OpenAPI) |
| **Datasets Provided** | Real-time cabled seafloor observatory data, underwater hydrophones, benthic cameras, acoustic Doppler current profilers, ocean bottom seismometers. |
| **Authentication Method** | HTTP Token Header (`token: <ONC_USER_TOKEN>`). |
| **Config Variable Name** | `ONC_USER_TOKEN` in `backend/.env`. |
| **Required Human Action** | 1. Create a free account at [data.oceannetworks.ca](https://data.oceannetworks.ca).<br>2. Generate an Oceans 3.0 API user token from Profile -> Web Services.<br>3. Set `ONC_USER_TOKEN=<token>` in `backend/.env`. |
| **Terms & Licence** | Open Data under CC-BY 4.0 with institutional attribution to University of Victoria / ONC. |
| **Integration Blocker** | Endpoint `https://data.oceannetworks.ca/api/archivefile` rejects unauthenticated requests with `HTTP 401`. |

---

### 2.4 FathomNet / MBARI — Automated Underwater Image Crawling

| Attribute | Detailed Specification |
| :--- | :--- |
| **Provider / Service** | FathomNet / MBARI Deep-Sea Benthic Image Database |
| **Official Website** | [https://fathomnet.org](https://fathomnet.org) |
| **API Endpoint** | `https://fathomnet.org/api` |
| **Datasets Provided** | Deep-sea benthic imagery annotated with Darwin Core concepts, bounding boxes, species labels, and ROV dive metadata. |
| **Authentication / Protection** | Cloudflare WAF / Anti-Bot challenge & rate-limiting gates automated headless crawlers (returns `HTTP 429` / `HTTP 403`). |
| **Config Variable Name** | `FATHOMNET_API_KEY` (if provisioned) or manual archive download. |
| **Required Human Action** | 1. Download the official static Darwin Core Archive (DwC-A) dump or community dataset export directly from [fathomnet.org](https://fathomnet.org).<br>2. Place the extracted archive in `backend/dataset-staging/fathomnet/`.<br>3. Run the offline batch loader `python -m app.modules.media.fathomnet_loader`. |
| **Terms & Licence** | Open Science CC-BY 4.0; requires attribution to MBARI, NOAA, and participating institutions. |
| **Integration Blocker** | Automated HTTP requests from server IP addresses encounter Cloudflare challenge pages (`HTTP 429 Too Many Requests`). |

---

### 2.5 Copernicus Marine Service — Unbounded Multi-Decadal Historical Reanalysis

| Attribute | Detailed Specification |
| :--- | :--- |
| **Provider / Service** | Copernicus Marine Service (Mercator Ocean International) |
| **Official Website** | [https://marine.copernicus.eu](https://marine.copernicus.eu) |
| **Datasets Provided** | Global Ocean Physics Reanalysis (1993-present, hourly/daily 3D grids of temperature, salinity, currents, mixed layer depth). Multi-gigabyte NetCDF downloads. |
| **Authentication Method** | Copernicus Marine User Account (`COPERNICUS_USERNAME` / `COPERNICUS_PASSWORD`). |
| **Config Variable Name** | `COPERNICUS_USERNAME` & `COPERNICUS_PASSWORD` in `backend/.env`. |
| **Required Human Action** | 1. Sign up for a free personal account at [marine.copernicus.eu](https://marine.copernicus.eu).<br>2. Enter credentials into `backend/.env`.<br>3. Verify login using `copernicusmarine login`. |
| **Terms & Licence** | Free, full, open and perpetual access under Copernicus Marine Data Policy. |
| **Integration Blocker** | The platform currently operates cleanly using verified local staging NetCDF files. Downloading fresh unbounded multi-decadal reanalysis sets requires active user authentication. |

---

## 3. Summary of Action Items for Platform Operator

When production access to these 5 services is required:
1. Obtain the 3 API tokens (`GFW_API_TOKEN`, `WDPA_API_TOKEN`, `ONC_USER_TOKEN`).
2. Add them to `backend/.env`.
3. Activate the corresponding ingestion adapters using their documented endpoints.
