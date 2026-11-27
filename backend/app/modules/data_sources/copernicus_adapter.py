"""
Copernicus Marine Service Provider Adapter.

Wraps the existing Copernicus retrieval and validation services into the
Unified Marine Data Provider interface (BaseMarineProvider).
"""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.modules.data_sources.base import (
    BaseMarineProvider,
    ProviderMetadata,
    ProviderDatasetMeta,
    UnifiedRetrievalParams,
    UnifiedPreviewResult,
    UnifiedRetrievalResult,
    UnifiedValidationResult,
    UnifiedProvenanceInfo,
    VariableStatsSummary,
)
from app.modules.data_sources.copernicus.dataset_registry import registry, RegisteredDataset
from app.modules.data_sources.copernicus.retrieval import retrieval_service, RetrievalParameters
from app.modules.data_sources.copernicus.validation import validator
from app.modules.data_sources.copernicus.service import search_catalogue as copernicus_search_catalogue
from app.modules.data_sources.copernicus.metadata import compute_sha256, build_provenance_record


class CopernicusMarineProvider(BaseMarineProvider):
    """Copernicus Marine Service implementation of BaseMarineProvider."""

    def __init__(self):
        self._metadata = ProviderMetadata(
            provider_id="copernicus",
            name="Copernicus Marine Service",
            organization="Mercator Ocean International / European Commission",
            base_url="https://marine.copernicus.eu",
            documentation_url="https://help.marine.copernicus.eu",
            access_method="copernicusmarine_toolbox",
            authentication_required=True,
            auth_description="Authentication token managed via copernicusmarine CLI credentials file (~/.copernicusmarine).",
            status="active",
            supported_formats=["NetCDF-4"],
            rate_limits_info="Standard institutional fair use, max 2500 deg² area limit per subset request",
            licence_info="Copernicus Open Access / CC-BY 4.0 License",
        )

    def metadata(self) -> ProviderMetadata:
        return self._metadata

    def list_datasets(self) -> List[ProviderDatasetMeta]:
        datasets = []
        for ds in registry.list_all():
            datasets.append(
                ProviderDatasetMeta(
                    provider_id="copernicus",
                    dataset_id=ds.dataset_id,
                    product_id=ds.product_id,
                    product_title=ds.product_title,
                    dataset_description=ds.dataset_description,
                    available_variables=ds.available_variables,
                    variable_metadata=ds.variable_metadata,
                    temporal_resolution=ds.temporal_resolution,
                    spatial_resolution=ds.spatial_resolution,
                    data_type=ds.data_type,
                    spatial_coverage=ds.spatial_coverage,
                    depth_levels_count=ds.depth_levels_count,
                    depth_min=ds.depth_min,
                    depth_max=ds.depth_max,
                    source_documentation=ds.source_documentation,
                    licence_information=ds.licence_information,
                    verification_status=ds.verification_status,
                )
            )
        return datasets

    def get_dataset(self, dataset_id: str) -> ProviderDatasetMeta:
        ds = registry.get_or_raise(dataset_id)
        return ProviderDatasetMeta(
            provider_id="copernicus",
            dataset_id=ds.dataset_id,
            product_id=ds.product_id,
            product_title=ds.product_title,
            dataset_description=ds.dataset_description,
            available_variables=ds.available_variables,
            variable_metadata=ds.variable_metadata,
            temporal_resolution=ds.temporal_resolution,
            spatial_resolution=ds.spatial_resolution,
            data_type=ds.data_type,
            spatial_coverage=ds.spatial_coverage,
            depth_levels_count=ds.depth_levels_count,
            depth_min=ds.depth_min,
            depth_max=ds.depth_max,
            source_documentation=ds.source_documentation,
            licence_information=ds.licence_information,
            verification_status=ds.verification_status,
        )

    def search_catalogue(
        self,
        keyword: str,
        limit: int = 10,
        data_type: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        return copernicus_search_catalogue(keyword=keyword, limit=limit)

    def validate_parameters(self, params: UnifiedRetrievalParams) -> None:
        c_params = RetrievalParameters(
            dataset_id=params.dataset_id,
            variables=params.variables,
            minimum_longitude=params.minimum_longitude,
            maximum_longitude=params.maximum_longitude,
            minimum_latitude=params.minimum_latitude,
            maximum_latitude=params.maximum_latitude,
            start_datetime=params.start_datetime,
            end_datetime=params.end_datetime,
            minimum_depth=params.minimum_depth,
            maximum_depth=params.maximum_depth,
            dataset_version=params.dataset_version,
            dataset_part=params.dataset_part,
            output_filename=params.output_filename,
        )
        retrieval_service.validate_parameters(c_params)

    def preview(self, params: UnifiedRetrievalParams, request_id: Optional[str] = None) -> UnifiedPreviewResult:
        c_params = RetrievalParameters(
            dataset_id=params.dataset_id,
            variables=params.variables,
            minimum_longitude=params.minimum_longitude,
            maximum_longitude=params.maximum_longitude,
            minimum_latitude=params.minimum_latitude,
            maximum_latitude=params.maximum_latitude,
            start_datetime=params.start_datetime,
            end_datetime=params.end_datetime,
            minimum_depth=params.minimum_depth,
            maximum_depth=params.maximum_depth,
            dataset_version=params.dataset_version,
            dataset_part=params.dataset_part,
        )
        res = retrieval_service.preview(c_params, request_id=request_id)
        
        lon_span = abs(params.maximum_longitude - params.minimum_longitude)
        lat_span = abs(params.maximum_latitude - params.minimum_latitude)
        area = lon_span * lat_span
        
        start_dt = datetime.fromisoformat(params.start_datetime.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(params.end_datetime.replace("Z", "+00:00"))
        duration = max(1.0, (end_dt - start_dt).total_seconds() / 86400.0)

        return UnifiedPreviewResult(
            request_id=res.request_id,
            provider_id="copernicus",
            dataset_id=params.dataset_id,
            estimated_size_mb=res.estimated_file_size_mb,
            estimated_total_points=None,
            bounding_box_area_deg2=round(area, 4),
            duration_days=round(duration, 2),
            status=res.dry_run_status,
            message=res.dry_run_message,
            selected_extent=res.selected_extent,
            variables=params.variables,
        )

    def retrieve(
        self,
        params: UnifiedRetrievalParams,
        job_id: str,
        staging_dir: Path,
    ) -> UnifiedRetrievalResult:
        c_params = RetrievalParameters(
            dataset_id=params.dataset_id,
            variables=params.variables,
            minimum_longitude=params.minimum_longitude,
            maximum_longitude=params.maximum_longitude,
            minimum_latitude=params.minimum_latitude,
            maximum_latitude=params.maximum_latitude,
            start_datetime=params.start_datetime,
            end_datetime=params.end_datetime,
            minimum_depth=params.minimum_depth,
            maximum_depth=params.maximum_depth,
            dataset_version=params.dataset_version,
            dataset_part=params.dataset_part,
            output_filename=params.output_filename,
        )
        job_dir = staging_dir / job_id
        downloaded = retrieval_service.execute_retrieval(
            params=c_params,
            job_id=job_id,
            custom_output_filename=params.output_filename,
            output_directory=job_dir,
        )
        file_size = downloaded.stat().st_size
        checksum = compute_sha256(downloaded)

        return UnifiedRetrievalResult(
            job_id=job_id,
            provider_id="copernicus",
            dataset_id=params.dataset_id,
            file_path=downloaded,
            file_format="NetCDF-4",
            file_size_bytes=file_size,
            sha256_checksum=checksum,
        )

    def validate_data(
        self,
        file_path: Path,
        params: UnifiedRetrievalParams,
    ) -> UnifiedValidationResult:
        rep = validator.validate_file(
            file_path=file_path,
            expected_dataset_id=params.dataset_id,
            expected_variables=params.variables,
            expected_bounds={
                "minimum_longitude": params.minimum_longitude,
                "maximum_longitude": params.maximum_longitude,
                "minimum_latitude": params.minimum_latitude,
                "maximum_latitude": params.maximum_latitude,
            },
            expected_start_time=params.start_datetime,
            expected_end_time=params.end_datetime,
            expected_depth_min=params.minimum_depth,
            expected_depth_max=params.maximum_depth,
        )

        var_stats = {}
        for vname, vs in rep.variable_stats.items():
            var_stats[vname] = VariableStatsSummary(
                variable_name=vs.variable_name,
                standard_name=vs.standard_name,
                units=vs.units,
                total_points=vs.total_points,
                valid_points=vs.valid_points,
                missing_points=vs.missing_points,
                out_of_range_points=vs.out_of_range_points,
                min_value=vs.min_value,
                max_value=vs.max_value,
                mean_value=vs.mean_value,
                std_value=vs.std_value,
                warnings=vs.warnings,
            )

        return UnifiedValidationResult(
            file_path=str(file_path),
            provider_id="copernicus",
            dataset_id=params.dataset_id,
            status=rep.status,
            is_valid=rep.is_valid,
            dimensions=rep.dimensions,
            coordinates_summary=rep.coordinates_summary,
            variable_stats=var_stats,
            cf_conventions=rep.cf_conventions,
            warnings=rep.warnings,
            errors=rep.errors,
        )

    def generate_provenance(
        self,
        job_id: str,
        retrieval_result: UnifiedRetrievalResult,
        validation_result: UnifiedValidationResult,
        params: UnifiedRetrievalParams,
    ) -> UnifiedProvenanceInfo:
        ds = registry.get_or_raise(params.dataset_id)
        prov = build_provenance_record(
            job_id=job_id,
            dataset_id=params.dataset_id,
            product_id=ds.product_id,
            requested_variables=params.variables,
            requested_spatial_extent={
                "minimum_longitude": params.minimum_longitude,
                "maximum_longitude": params.maximum_longitude,
                "minimum_latitude": params.minimum_latitude,
                "maximum_latitude": params.maximum_latitude,
            },
            requested_time_interval={
                "start": params.start_datetime,
                "end": params.end_datetime,
            },
            file_path=retrieval_result.file_path,
            dataset_version=ds.dataset_version,
            dataset_part=ds.dataset_part,
        )

        return UnifiedProvenanceInfo(
            job_id=job_id,
            provider="Copernicus Marine Service",
            product_id=ds.product_id,
            dataset_id=params.dataset_id,
            dataset_version=ds.dataset_version,
            retrieval_timestamp=prov["retrieval_timestamp"],
            requested_date_range=prov["requested_date_range"],
            actual_data_date_range=prov["actual_data_date_range"],
            spatial_extent=prov["spatial_extent"],
            variables=prov["variables"],
            units=prov["units"],
            processing_method=prov["processing_method"],
            source_licence=prov["source_licence"],
            toolbox_version=prov["toolbox_version"],
            sha256_checksum=prov["sha256_checksum"],
        )
