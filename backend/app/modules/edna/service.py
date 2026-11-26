"""
Environmental DNA (eDNA) Workflow and Taxonomic Assignment Service.

Manages:
- Field collection metadata (depth, Niskin filtration, volume, spatial coordinates).
- Fastq sequence file references in the marine-edna SeaweedFS bucket.
- ASV taxonomic assignments reconciled against WoRMS AphiaID.
- Strict scientific interpretation safeguards (molecular detection != confirmed presence).
"""

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Any
import uuid

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.database.models import EDNASampleModel, EDNATaxonomicAssignmentModel
from app.modules.data_sources.worms.service import worms_service

logger = logging.getLogger(__name__)

SAFEGUARD_NOTE = (
    "Sequence match constitutes molecular detection only; "
    "physical organism presence requires ecological and oceanographic validation."
)


class EDNAWorkflowService:
    """Service managing eDNA sample registries, sequence references, and taxonomic matches."""

    def create_sample(
        self,
        db: Session,
        sample_code: str,
        project_id: str,
        latitude: float,
        longitude: float,
        target_gene: str,
        collected_at: datetime,
        collection_depth_m: Optional[float] = None,
        water_body: Optional[str] = None,
        expedition_id: Optional[str] = None,
        station_id: Optional[str] = None,
        collection_method: Optional[str] = "Niskin bottle filtration",
        preservation_method: Optional[str] = "Longmire buffer",
        extraction_protocol: Optional[str] = "DNeasy Blood & Tissue",
        primer_forward: Optional[str] = None,
        primer_reverse: Optional[str] = None,
        sequencing_platform: Optional[str] = "Illumina NovaSeq",
        raw_fastq_forward_key: Optional[str] = None,
        raw_fastq_reverse_key: Optional[str] = None,
        sha256_checksum: Optional[str] = None,
    ) -> EDNASampleModel:
        """Registers new eDNA field sample with spatial point and sequencing metadata."""
        # PostGIS geometry creation when connected to PostgreSQL
        geom_val = None
        if db.bind and db.bind.dialect.name == "postgresql":
            geom_val = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)

        sample = EDNASampleModel(
            id=str(uuid.uuid4()),
            sample_code=sample_code,
            project_id=project_id,
            expedition_id=expedition_id,
            station_id=station_id,
            geom=geom_val,
            latitude=latitude,
            longitude=longitude,
            collection_depth_m=collection_depth_m,
            water_body=water_body,
            collected_at=collected_at,
            collection_method=collection_method,
            preservation_method=preservation_method,
            extraction_protocol=extraction_protocol,
            target_gene=target_gene,
            primer_forward=primer_forward,
            primer_reverse=primer_reverse,
            sequencing_platform=sequencing_platform,
            raw_fastq_forward_key=raw_fastq_forward_key,
            raw_fastq_reverse_key=raw_fastq_reverse_key,
            sha256_checksum=sha256_checksum,
        )
        db.add(sample)
        db.commit()
        db.refresh(sample)
        return sample

    def list_samples(
        self,
        db: Session,
        project_id: Optional[str] = None,
        target_gene: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Queries eDNA samples with filtering."""
        query = select(EDNASampleModel)
        count_query = select(func.count(EDNASampleModel.id))

        filters = []
        if project_id:
            filters.append(EDNASampleModel.project_id == project_id)
        if target_gene:
            filters.append(EDNASampleModel.target_gene == target_gene)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = db.scalar(count_query) or 0
        records = db.execute(query.order_by(EDNASampleModel.collected_at.desc()).offset(offset).limit(limit)).scalars().all()

        samples = []
        for s in records:
            samples.append({
                "id": s.id,
                "sample_code": s.sample_code,
                "project_id": s.project_id,
                "expedition_id": s.expedition_id,
                "station_id": s.station_id,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "collection_depth_m": s.collection_depth_m,
                "water_body": s.water_body,
                "collected_at": s.collected_at.isoformat() if s.collected_at else None,
                "target_gene": s.target_gene,
                "sequencing_platform": s.sequencing_platform,
                "raw_fastq_forward_key": s.raw_fastq_forward_key,
                "raw_fastq_reverse_key": s.raw_fastq_reverse_key,
                "sha256_checksum": s.sha256_checksum,
            })

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "samples": samples,
        }

    def get_sample_details(self, db: Session, sample_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves single eDNA sample with all its taxonomic assignment records."""
        sample = db.execute(
            select(EDNASampleModel).where(
                (EDNASampleModel.id == sample_id) | (EDNASampleModel.sample_code == sample_id)
            )
        ).scalar_one_or_none()

        if not sample:
            return None

        # Fetch assignments
        assignments_records = db.execute(
            select(EDNATaxonomicAssignmentModel)
            .where(EDNATaxonomicAssignmentModel.sample_id == sample.id)
            .order_by(EDNATaxonomicAssignmentModel.read_count.desc())
        ).scalars().all()

        assignments = []
        for a in assignments_records:
            assignments.append({
                "id": a.id,
                "asv_sequence_id": a.asv_sequence_id,
                "sequence_header": a.sequence_header,
                "read_count": a.read_count,
                "matched_scientific_name": a.matched_scientific_name,
                "aphia_id": a.aphia_id,
                "taxonomic_rank": a.taxonomic_rank,
                "identity_percent": a.identity_percent,
                "confidence_score": a.confidence_score,
                "reference_database": a.reference_database,
                "scientific_interpretation_notes": a.scientific_interpretation_notes,
            })

        return {
            "id": sample.id,
            "sample_code": sample.sample_code,
            "project_id": sample.project_id,
            "expedition_id": sample.expedition_id,
            "station_id": sample.station_id,
            "latitude": sample.latitude,
            "longitude": sample.longitude,
            "collection_depth_m": sample.collection_depth_m,
            "water_body": sample.water_body,
            "collected_at": sample.collected_at.isoformat() if sample.collected_at else None,
            "collection_method": sample.collection_method,
            "preservation_method": sample.preservation_method,
            "extraction_protocol": sample.extraction_protocol,
            "target_gene": sample.target_gene,
            "primer_forward": sample.primer_forward,
            "primer_reverse": sample.primer_reverse,
            "sequencing_platform": sample.sequencing_platform,
            "raw_fastq_forward_key": sample.raw_fastq_forward_key,
            "raw_fastq_reverse_key": sample.raw_fastq_reverse_key,
            "sha256_checksum": sample.sha256_checksum,
            "assignments_count": len(assignments),
            "taxonomic_assignments": assignments,
        }

    def add_taxonomic_assignment(
        self,
        db: Session,
        sample_id: str,
        asv_sequence_id: str,
        matched_scientific_name: str,
        read_count: int,
        identity_percent: float,
        confidence_score: float,
        reference_database: str = "MitoFish",
        sequence_header: Optional[str] = None,
        custom_interpretation: Optional[str] = None,
    ) -> EDNATaxonomicAssignmentModel:
        """
        Adds taxonomic assignment for an eDNA sample.
        Reconciles matched scientific name against WoRMS to retrieve AphiaID.
        Enforces scientific interpretation safeguard note.
        """
        # Resolve AphiaID via WoRMS
        aphia_id = None
        rank = None
        try:
            lookup = worms_service.lookup_by_name(matched_scientific_name, db=db, marine_only=False)
            if lookup:
                aphia_id = lookup[0].get("aphia_id")
                rank = lookup[0].get("rank")
        except Exception as exc:
            logger.warning(f"WoRMS lookup skipped during eDNA assignment for {matched_scientific_name}: {exc}")

        notes = custom_interpretation or SAFEGUARD_NOTE

        assignment = EDNATaxonomicAssignmentModel(
            id=str(uuid.uuid4()),
            sample_id=sample_id,
            asv_sequence_id=asv_sequence_id,
            sequence_header=sequence_header,
            read_count=read_count,
            matched_scientific_name=matched_scientific_name,
            aphia_id=aphia_id,
            taxonomic_rank=rank or "Species",
            identity_percent=identity_percent,
            confidence_score=confidence_score,
            reference_database=reference_database,
            scientific_interpretation_notes=notes,
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return assignment


edna_service = EDNAWorkflowService()
