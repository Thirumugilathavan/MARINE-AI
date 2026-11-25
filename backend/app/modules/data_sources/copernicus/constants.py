"""
Verified Copernicus Marine Service dataset definitions and constants.

All dataset IDs defined here are verified against the live Copernicus Marine Data Store
(Marine Data Store / STAC catalogue API).
"""

from typing import Dict, List, Any

# ==============================================================================
# Verified Copernicus Dataset Identifiers
# ==============================================================================

# 1. NRT Six-Hourly (PT6H-i) - Global Ocean Physics Analysis & Forecast
# Product: GLOBAL_ANALYSISFORECAST_PHY_001_024
DATASET_NRT_SIX_HOURLY_THETAO = "cmems_mod_glo_phy-thetao_anfc_0.083deg_PT6H-i"
DATASET_NRT_SIX_HOURLY_SO = "cmems_mod_glo_phy-so_anfc_0.083deg_PT6H-i"
DATASET_NRT_SIX_HOURLY_CURRENTS = "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i"

# 2. NRT Daily (P1D-m) - Global Ocean Physics Analysis & Forecast
# Product: GLOBAL_ANALYSISFORECAST_PHY_001_024
DATASET_NRT_DAILY_THETAO = "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m"
DATASET_NRT_DAILY_SO = "cmems_mod_glo_phy-so_anfc_0.083deg_P1D-m"
DATASET_NRT_DAILY_CURRENTS = "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m"

# 3. Historical Daily Reanalysis (P1D-m) - Global Ocean Physics Reanalysis
# Product: GLOBAL_MULTIYEAR_PHY_001_030
DATASET_HISTORICAL_DAILY = "cmems_mod_glo_phy_my_0.083deg_P1D-m"


# ==============================================================================
# Target Region: Indian Ocean Bounding Box (Configurable)
# ==============================================================================
DEFAULT_INDIAN_OCEAN_BOUNDS = {
    "minimum_longitude": 30.0,
    "maximum_longitude": 120.0,
    "minimum_latitude": -30.0,
    "maximum_latitude": 30.0,
}


# ==============================================================================
# Supported Oceanographic Variables & Units
# ==============================================================================
SUPPORTED_VARIABLES: Dict[str, Dict[str, Any]] = {
    "thetao": {
        "name": "Sea water potential temperature",
        "units": "degrees_C",
        "standard_name": "sea_water_potential_temperature",
        "min_valid_physical": -3.0,
        "max_valid_physical": 45.0,
    },
    "so": {
        "name": "Sea water salinity",
        "units": "1e-3",
        "standard_name": "sea_water_salinity",
        "min_valid_physical": 0.0,
        "max_valid_physical": 50.0,
    },
    "uo": {
        "name": "Eastward sea water velocity",
        "units": "m s-1",
        "standard_name": "eastward_sea_water_velocity",
        "min_valid_physical": -15.0,
        "max_valid_physical": 15.0,
    },
    "vo": {
        "name": "Northward sea water velocity",
        "units": "m s-1",
        "standard_name": "northward_sea_water_velocity",
        "min_valid_physical": -15.0,
        "max_valid_physical": 15.0,
    },
}


# ==============================================================================
# Cadence to Dataset Mappings
# ==============================================================================
CADENCE_DATASET_MAP: Dict[str, Dict[str, Any]] = {
    "nrt_six_hourly": {
        "cadence_label": "Near-Real-Time Six-Hourly Instantaneous",
        "time_resolution": "PT6H",
        "update_frequency": "4 daily forecast cycles (00:00, 06:00, 12:00, 18:00 UTC)",
        "product_id": "GLOBAL_ANALYSISFORECAST_PHY_001_024",
        "spatial_resolution": "0.083 deg (~1/12 degree)",
        "variable_datasets": {
            "thetao": DATASET_NRT_SIX_HOURLY_THETAO,
            "so": DATASET_NRT_SIX_HOURLY_SO,
            "uo": DATASET_NRT_SIX_HOURLY_CURRENTS,
            "vo": DATASET_NRT_SIX_HOURLY_CURRENTS,
        },
    },
    "nrt_daily": {
        "cadence_label": "Near-Real-Time Daily Mean",
        "time_resolution": "P1D",
        "update_frequency": "Daily",
        "product_id": "GLOBAL_ANALYSISFORECAST_PHY_001_024",
        "spatial_resolution": "0.083 deg (~1/12 degree)",
        "variable_datasets": {
            "thetao": DATASET_NRT_DAILY_THETAO,
            "so": DATASET_NRT_DAILY_SO,
            "uo": DATASET_NRT_DAILY_CURRENTS,
            "vo": DATASET_NRT_DAILY_CURRENTS,
        },
    },
    "historical_daily": {
        "cadence_label": "Historical Daily Mean Reanalysis",
        "time_resolution": "P1D",
        "update_frequency": "Historical reanalysis (1993 to multi-year archive)",
        "product_id": "GLOBAL_MULTIYEAR_PHY_001_030",
        "spatial_resolution": "0.083 deg (~1/12 degree)",
        "variable_datasets": {
            "thetao": DATASET_HISTORICAL_DAILY,
            "so": DATASET_HISTORICAL_DAILY,
            "uo": DATASET_HISTORICAL_DAILY,
            "vo": DATASET_HISTORICAL_DAILY,
        },
    },
}
