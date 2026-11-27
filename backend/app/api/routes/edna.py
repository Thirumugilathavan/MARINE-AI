"""
FastAPI Routes for Environmental DNA (eDNA) Workflow and Taxonomic Assignments.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.modules.edna.service import edna_service

router = APIRouter(prefix="/edna", tags=["eDNA Research Workflow"])


class EDNASampleCreateRequest(BaseModel):
    sample_code: str = Field(..., description="Unique field sample identifier e.g. 'IO-2024-ST01-EDNA'")
    project_id: str = Field(..., description="Project / Cruise identifier e.g. 'SIH-INDIAN-OCEAN-2024'")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    target_gene: str = Field(..., description="Marker gene locus e.g. '12S', '16S', 'COI'")
    collected_at: Optional[datetime] = None
    collection_depth_m: Optional[float] = Field(None, ge=0.0)
    water_body: Optional[str] = "Indian Ocean"
    expedition_id: Optional[str] = None
    station_id: Optional[str] = None
    collection_method: Optional[str] = "Niskin bottle filtration"
    preservation_method: Optional[str] = "Longmire buffer"
    extraction_protocol: Optional[str] = "DNeasy Blood & Tissue"
    primer_forward: Optional[str] = None
    primer_reverse: Optional[str] = None
    sequencing_platform: Optional[str] = "Illumina NovaSeq"
    raw_fastq_forward_key: Optional[str] = None
    raw_fastq_reverse_key: Optional[str] = None
    sha256_checksum: Optional[str] = None


class TaxonomicAssignmentCreateRequest(BaseModel):
    asv_sequence_id: str = Field(..., description="ASV identifier or Amplicon ID e.g. 'ASV_00124'")
    matched_scientific_name: str = Field(..., description="Assigned scientific name e.g. 'Thunnus albacares'")
    read_count: int = Field(1, ge=1)
    identity_percent: float = Field(..., ge=0.0, le=100.0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    reference_database: str = Field("MitoFish", description="Reference database used (MitoFish, SILVA, NCBI-nt, PR2)")
    sequence_header: Optional[str] = None
    custom_interpretation: Optional[str] = None


class EDNASampleSummary(BaseModel):
    id: str
    sample_code: str
    project_id: str
    latitude: float
    longitude: float
    target_gene: str
    collection_depth_m: Optional[float] = None
    water_body: Optional[str] = None
    sequencing_platform: Optional[str] = None
    created_at: Optional[datetime] = None


class EDNASampleListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    samples: List[EDNASampleSummary]


@router.post("/samples", status_code=status.HTTP_201_CREATED)
def create_edna_sample(
    payload: EDNASampleCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Registers a new marine eDNA sample with spatial coordinates,
    sampling depth, target marker locus, and FASTQ reference keys.
    """
    try:
        sample = edna_service.create_sample(
            db=db,
            sample_code=payload.sample_code,
            project_id=payload.project_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            target_gene=payload.target_gene,
            collected_at=payload.collected_at or datetime.now(timezone.utc),
            collection_depth_m=payload.collection_depth_m,
            water_body=payload.water_body,
            expedition_id=payload.expedition_id,
            station_id=payload.station_id,
            collection_method=payload.collection_method,
            preservation_method=payload.preservation_method,
            extraction_protocol=payload.extraction_protocol,
            primer_forward=payload.primer_forward,
            primer_reverse=payload.primer_reverse,
            sequencing_platform=payload.sequencing_platform,
            raw_fastq_forward_key=payload.raw_fastq_forward_key,
            raw_fastq_reverse_key=payload.raw_fastq_reverse_key,
            sha256_checksum=payload.sha256_checksum,
        )
        return {
            "status": "success",
            "sample_id": sample.id,
            "sample_code": sample.sample_code,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create eDNA sample: {str(exc)}",
        )


@router.get("/samples", response_model=EDNASampleListResponse)
def list_edna_samples(
    project_id: Optional[str] = Query(None),
    target_gene: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Queries registered eDNA samples.
    """
    return edna_service.list_samples(
        db=db,
        project_id=project_id,
        target_gene=target_gene,
        limit=limit,
        offset=offset,
    )


@router.get("/samples/{sample_id}")
def get_edna_sample_details(
    sample_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieves eDNA sample details including all identified ASV taxonomic assignments.
    """
    details = edna_service.get_sample_details(db=db, sample_id=sample_id)
    if not details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"eDNA sample '{sample_id}' not found",
        )
    return details


@router.post("/samples/{sample_id}/assignments", status_code=status.HTTP_201_CREATED)
def add_taxonomic_assignment(
    sample_id: str,
    payload: TaxonomicAssignmentCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Adds a taxonomic assignment to an eDNA sample.
    Reconciles the matched species against WoRMS for authoritative AphiaID.
    Applies scientific interpretation safeguard.
    """
    # Verify sample exists
    sample = edna_service.get_sample_details(db=db, sample_id=sample_id)
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"eDNA sample '{sample_id}' not found",
        )

    try:
        assignment = edna_service.add_taxonomic_assignment(
            db=db,
            sample_id=sample["id"],
            asv_sequence_id=payload.asv_sequence_id,
            matched_scientific_name=payload.matched_scientific_name,
            read_count=payload.read_count,
            identity_percent=payload.identity_percent,
            confidence_score=payload.confidence_score,
            reference_database=payload.reference_database,
            sequence_header=payload.sequence_header,
            custom_interpretation=payload.custom_interpretation,
        )
        return {
            "status": "success",
            "assignment_id": assignment.id,
            "matched_scientific_name": assignment.matched_scientific_name,
            "aphia_id": assignment.aphia_id,
            "scientific_interpretation_notes": assignment.scientific_interpretation_notes,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to add taxonomic assignment: {str(exc)}",
        )
