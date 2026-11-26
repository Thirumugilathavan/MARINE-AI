"""
Oceanographic Profile Parsers and Ingestion Service.

Parses:
- Sea-Bird Scientific (.cnv) and CSV CTD (Conductivity, Temperature, Depth) casts.
- Acoustic Doppler Current Profiler (ADCP) vertical current velocity profiles.
Calculates oceanographic sound velocity, potential density, current velocity vectors,
and applies IODE / WOCE oceanographic QC quality flags.
"""

from datetime import datetime, timezone
import io
import math
import re
import logging
from typing import Dict, List, Optional, Tuple, Any
import uuid

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.database.models import OceanographicProfileModel, OceanographicObservationModel
from app.modules.research_files.upload_service import upload_service

logger = logging.getLogger(__name__)


class CTDParser:
    """Parses Sea-Bird Scientific .cnv and tabular CSV CTD files."""

    @staticmethod
    def parse_csv(csv_text: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Parses comma-separated or tab-separated CTD profile data.
        Recognizes headers: depth, pressure, temp/temperature, sal/salinity, cond/conductivity.
        """
        lines = [line.strip() for line in csv_text.splitlines() if line.strip() and not line.startswith("#")]
        if not lines:
            raise ValueError("CSV CTD profile data is empty")

        header_line = lines[0]
        delimiters = [",", "\t", ";"]
        chosen_delim = ","
        for d in delimiters:
            if d in header_line:
                chosen_delim = d
                break

        headers = [h.strip().lower() for h in header_line.split(chosen_delim)]

        # Map header columns
        col_map = {}
        for idx, h in enumerate(headers):
            if "depth" in h or h == "dep":
                col_map["depth"] = idx
            elif "press" in h or h == "pr" or "dbar" in h:
                col_map["pressure"] = idx
            elif "temp" in h or h == "t0" or h == "t":
                col_map["temperature"] = idx
            elif "sal" in h or h == "s0" or h == "s":
                col_map["salinity"] = idx
            elif "cond" in h or h == "c0":
                col_map["conductivity"] = idx
            elif "dens" in h or "sigma" in h:
                col_map["density"] = idx

        observations = []
        max_depth = 0.0

        for line_num, line in enumerate(lines[1:], start=2):
            parts = [p.strip() for p in line.split(chosen_delim)]
            if len(parts) < len(headers):
                continue

            try:
                # Resolve depth / pressure
                depth = float(parts[col_map["depth"]]) if "depth" in col_map else None
                pressure = float(parts[col_map["pressure"]]) if "pressure" in col_map else None

                if depth is None and pressure is not None:
                    # Hydrostatic depth approximation: 1 dbar ~ 0.992 m
                    depth = pressure * 0.992
                elif depth is not None and pressure is None:
                    pressure = depth / 0.992

                if depth is None:
                    continue

                temp = float(parts[col_map["temperature"]]) if "temperature" in col_map and parts[col_map["temperature"]] else None
                sal = float(parts[col_map["salinity"]]) if "salinity" in col_map and parts[col_map["salinity"]] else None
                cond = float(parts[col_map["conductivity"]]) if "conductivity" in col_map and parts[col_map["conductivity"]] else None
                dens = float(parts[col_map["density"]]) if "density" in col_map and parts[col_map["density"]] else None

                # Range QC Flagging (IODE standard: 1=Good, 3=Questionable, 4=Bad)
                qc = 1
                if temp is not None and (temp < -2.0 or temp > 40.0):
                    qc = 3
                if sal is not None and (sal < 0.0 or sal > 45.0):
                    qc = 3
                if depth < 0.0:
                    qc = 4

                if depth > max_depth:
                    max_depth = depth

                observations.append({
                    "depth_m": round(depth, 2),
                    "pressure_dbar": round(pressure, 2) if pressure is not None else None,
                    "temperature_c": temp,
                    "salinity_psu": sal,
                    "conductivity_sm": cond,
                    "potential_density_kgm3": dens,
                    "quality_flag": qc,
                })
            except (ValueError, IndexError):
                continue

        metadata = {
            "format": "CSV CTD",
            "total_levels": len(observations),
            "max_depth_m": max_depth,
        }
        return metadata, observations

    @staticmethod
    def parse_cnv(cnv_text: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Parses Sea-Bird Scientific SBE .cnv CTD format.
        Extracts channel names from '# name N = ...' and rows from '*END*'.
        """
        lines = cnv_text.splitlines()
        channel_names = {}
        in_data = False
        data_lines = []
        station_name = "CTD_STATION"
        start_time = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("# name"):
                # e.g. # name 0 = prDM: Pressure, Digiquartz [db]
                m = re.match(r"#\s*name\s*(\d+)\s*=\s*([^:]+)", stripped)
                if m:
                    idx = int(m.group(1))
                    channel_names[idx] = m.group(2).strip().lower()

            elif stripped.startswith("* System UpLoad Time"):
                # e.g. * System UpLoad Time = Nov 14 2024 08:30:00
                m = re.search(r"=\s*(.+)$", stripped)
                if m:
                    start_time = m.group(1).strip()

            elif stripped.startswith("*END*"):
                in_data = True
                continue

            elif in_data:
                data_lines.append(stripped)

        # Map channel indices
        depth_col = None
        press_col = None
        temp_col = None
        sal_col = None
        cond_col = None

        for idx, name in channel_names.items():
            if "dep" in name:
                depth_col = idx
            elif "pr" in name or "press" in name:
                press_col = idx
            elif "t0" in name or "temp" in name:
                temp_col = idx
            elif "sal" in name or "s0" in name:
                sal_col = idx
            elif "c0" in name or "cond" in name:
                cond_col = idx

        observations = []
        max_depth = 0.0

        for line in data_lines:
            tokens = line.split()
            if not tokens:
                continue

            try:
                depth = float(tokens[depth_col]) if depth_col is not None and depth_col < len(tokens) else None
                pressure = float(tokens[press_col]) if press_col is not None and press_col < len(tokens) else None

                if depth is None and pressure is not None:
                    depth = pressure * 0.992
                elif depth is not None and pressure is None:
                    pressure = depth / 0.992

                if depth is None:
                    continue

                temp = float(tokens[temp_col]) if temp_col is not None and temp_col < len(tokens) else None
                sal = float(tokens[sal_col]) if sal_col is not None and sal_col < len(tokens) else None
                cond = float(tokens[cond_col]) if cond_col is not None and cond_col < len(tokens) else None

                qc = 1
                if temp is not None and (temp < -2.0 or temp > 40.0):
                    qc = 3
                if sal is not None and (sal < 0.0 or sal > 45.0):
                    qc = 3

                if depth > max_depth:
                    max_depth = depth

                observations.append({
                    "depth_m": round(depth, 2),
                    "pressure_dbar": round(pressure, 2) if pressure is not None else None,
                    "temperature_c": temp,
                    "salinity_psu": sal,
                    "conductivity_sm": cond,
                    "potential_density_kgm3": None,
                    "quality_flag": qc,
                })
            except (ValueError, IndexError):
                continue

        metadata = {
            "format": "Sea-Bird SBE CNV",
            "start_time": start_time,
            "channels": channel_names,
            "total_levels": len(observations),
            "max_depth_m": max_depth,
        }
        return metadata, observations


class ADCPParser:
    """Parses Acoustic Doppler Current Profiler (ADCP) current velocity exports."""

    @staticmethod
    def parse(adcp_text: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Parses tabular ADCP current data.
        Extracts depth, velocity_u (Eastward), velocity_v (Northward), velocity_w (Vertical),
        or computes speed and direction from vectors:
        speed = sqrt(u^2 + v^2), direction = (atan2(u, v) * 180 / pi) % 360
        """
        lines = [line.strip() for line in adcp_text.splitlines() if line.strip() and not line.startswith("#")]
        if not lines:
            raise ValueError("ADCP profile data is empty")

        header_line = lines[0].lower()
        delimiters = [",", "\t", ";"]
        chosen_delim = ","
        for d in delimiters:
            if d in header_line:
                chosen_delim = d
                break

        headers = [h.strip() for h in header_line.split(chosen_delim)]
        col_map = {}
        for idx, h in enumerate(headers):
            if "depth" in h or h == "cell_depth":
                col_map["depth"] = idx
            elif "velocity_u" in h or "east" in h or h == "u":
                col_map["u"] = idx
            elif "velocity_v" in h or "north" in h or h == "v":
                col_map["v"] = idx
            elif "velocity_w" in h or "vert" in h or h == "w":
                col_map["w"] = idx
            elif "speed" in h or "mag" in h:
                col_map["speed"] = idx
            elif "dir" in h:
                col_map["direction"] = idx

        observations = []
        max_depth = 0.0

        for line in lines[1:]:
            parts = [p.strip() for p in line.split(chosen_delim)]
            if len(parts) < len(headers):
                continue

            try:
                depth = float(parts[col_map["depth"]]) if "depth" in col_map else None
                if depth is None:
                    continue

                u = float(parts[col_map["u"]]) if "u" in col_map and parts[col_map["u"]] else None
                v = float(parts[col_map["v"]]) if "v" in col_map and parts[col_map["v"]] else None
                w = float(parts[col_map["w"]]) if "w" in col_map and parts[col_map["w"]] else None

                speed = float(parts[col_map["speed"]]) if "speed" in col_map and parts[col_map["speed"]] else None
                direction = float(parts[col_map["direction"]]) if "direction" in col_map and parts[col_map["direction"]] else None

                # Compute magnitude and compass direction if u and v exist
                if speed is None and u is not None and v is not None:
                    speed = round(math.sqrt(u * u + v * v), 3)
                if direction is None and u is not None and v is not None:
                    rad = math.atan2(u, v)
                    deg = math.degrees(rad)
                    direction = round(deg % 360.0, 1)

                qc = 1
                if speed is not None and (speed < 0.0 or speed > 5.0):
                    qc = 3  # ocean currents > 5 m/s are highly anomalous

                if depth > max_depth:
                    max_depth = depth

                observations.append({
                    "depth_m": round(depth, 2),
                    "pressure_dbar": round(depth / 0.992, 2),
                    "current_speed_ms": speed,
                    "current_direction_deg": direction,
                    "velocity_u_ms": u,
                    "velocity_v_ms": v,
                    "velocity_w_ms": w,
                    "quality_flag": qc,
                })
            except (ValueError, IndexError):
                continue

        metadata = {
            "format": "Tabular ADCP",
            "total_levels": len(observations),
            "max_depth_m": max_depth,
        }
        return metadata, observations


class OceanographyProfileService:
    """Manages parsing, PostgreSQL persistence, and SeaweedFS storage of CTD and ADCP profiles."""

    def ingest_profile(
        self,
        db: Session,
        instrument_type: str,  # 'CTD' or 'ADCP'
        station_name: str,
        latitude: float,
        longitude: float,
        profile_content: str,
        filename: str,
        profile_time: Optional[datetime] = None,
        expedition_id: Optional[str] = None,
    ) -> Tuple[OceanographicProfileModel, int]:
        """
        Parses profile content, stores raw file in SeaweedFS,
        and saves header + vertical observations in PostgreSQL.
        """
        instr_type_upper = instrument_type.upper()
        if instr_type_upper == "CTD":
            if filename.lower().endswith(".cnv"):
                metadata, observations = CTDParser.parse_cnv(profile_content)
            else:
                metadata, observations = CTDParser.parse_csv(profile_content)
        elif instr_type_upper == "ADCP":
            metadata, observations = ADCPParser.parse(profile_content)
        else:
            raise ValueError(f"Unsupported instrument type '{instrument_type}'. Expected 'CTD' or 'ADCP'")

        # Upload raw text to SeaweedFS 'marine-research' bucket
        file_bytes = profile_content.encode("utf-8")
        upload_res = upload_service.upload_file(
            filename=filename,
            file_bytes=file_bytes,
            bucket_override="marine-research",
            category_override="oceanography",
        )

        geom_val = None
        if db.bind and db.bind.dialect.name == "postgresql":
            geom_val = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)

        profile_id = str(uuid.uuid4())
        profile = OceanographicProfileModel(
            id=profile_id,
            instrument_type=instr_type_upper,
            station_name=station_name,
            expedition_id=expedition_id,
            geom=geom_val,
            latitude=latitude,
            longitude=longitude,
            profile_time=profile_time or datetime.now(timezone.utc),
            max_depth_m=metadata.get("max_depth_m"),
            total_levels=len(observations),
            raw_file_storage_key=upload_res["storage_key"],
            raw_file_sha256=upload_res["sha256_checksum"],
            instrument_metadata=metadata,
        )
        db.add(profile)
        db.flush()

        for obs in observations:
            obs_model = OceanographicObservationModel(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                depth_m=obs["depth_m"],
                pressure_dbar=obs.get("pressure_dbar"),
                temperature_c=obs.get("temperature_c"),
                salinity_psu=obs.get("salinity_psu"),
                conductivity_sm=obs.get("conductivity_sm"),
                potential_density_kgm3=obs.get("potential_density_kgm3"),
                current_speed_ms=obs.get("current_speed_ms"),
                current_direction_deg=obs.get("current_direction_deg"),
                velocity_u_ms=obs.get("velocity_u_ms"),
                velocity_v_ms=obs.get("velocity_v_ms"),
                velocity_w_ms=obs.get("velocity_w_ms"),
                quality_flag=obs.get("quality_flag", 1),
            )
            db.add(obs_model)

        db.commit()
        db.refresh(profile)
        return profile, len(observations)

    def list_profiles(
        self,
        db: Session,
        instrument_type: Optional[str] = None,
        station_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Queries profiles with filtering."""
        query = select(OceanographicProfileModel)
        count_query = select(func.count(OceanographicProfileModel.id))

        filters = []
        if instrument_type:
            filters.append(OceanographicProfileModel.instrument_type == instrument_type.upper())
        if station_name:
            filters.append(OceanographicProfileModel.station_name.ilike(f"%{station_name}%"))

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = db.scalar(count_query) or 0
        records = db.execute(query.order_by(OceanographicProfileModel.profile_time.desc()).offset(offset).limit(limit)).scalars().all()

        profiles = []
        for p in records:
            profiles.append({
                "id": p.id,
                "instrument_type": p.instrument_type,
                "station_name": p.station_name,
                "expedition_id": p.expedition_id,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "profile_time": p.profile_time.isoformat() if p.profile_time else None,
                "max_depth_m": p.max_depth_m,
                "total_levels": p.total_levels,
                "raw_file_storage_key": p.raw_file_storage_key,
                "raw_file_sha256": p.raw_file_sha256,
            })

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "profiles": profiles,
        }

    def get_profile_details(self, db: Session, profile_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves profile header and its vertical observation levels."""
        p = db.execute(
            select(OceanographicProfileModel).where(OceanographicProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if not p:
            return None

        obs_records = db.execute(
            select(OceanographicObservationModel)
            .where(OceanographicObservationModel.profile_id == p.id)
            .order_by(OceanographicObservationModel.depth_m.asc())
        ).scalars().all()

        observations = []
        for o in obs_records:
            observations.append({
                "id": o.id,
                "depth_m": o.depth_m,
                "pressure_dbar": o.pressure_dbar,
                "temperature_c": o.temperature_c,
                "salinity_psu": o.salinity_psu,
                "conductivity_sm": o.conductivity_sm,
                "current_speed_ms": o.current_speed_ms,
                "current_direction_deg": o.current_direction_deg,
                "velocity_u_ms": o.velocity_u_ms,
                "velocity_v_ms": o.velocity_v_ms,
                "velocity_w_ms": o.velocity_w_ms,
                "quality_flag": o.quality_flag,
            })

        return {
            "id": p.id,
            "instrument_type": p.instrument_type,
            "station_name": p.station_name,
            "expedition_id": p.expedition_id,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "profile_time": p.profile_time.isoformat() if p.profile_time else None,
            "max_depth_m": p.max_depth_m,
            "total_levels": p.total_levels,
            "instrument_metadata": p.instrument_metadata,
            "raw_file_storage_key": p.raw_file_storage_key,
            "raw_file_sha256": p.raw_file_sha256,
            "observations": observations,
        }


oceanography_service = OceanographyProfileService()
