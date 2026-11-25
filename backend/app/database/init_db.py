"""
Database initialization utilities.

Safely initializes database tables using SQLAlchemy's checkfirst=True policy,
ensuring that existing tables and data are never dropped or damaged, and
seeds the provider registry and verified dataset definitions across providers.
"""

import logging
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from app.database.connection import engine
from app.database.models import Base, DataProviderModel, DatasetRegistryModel

logger = logging.getLogger(__name__)


def seed_providers_and_datasets(target_engine: Engine = engine) -> None:
    """
    Seeds verified providers and datasets from provider_registry into the database
    if they do not already exist, preserving all existing records.
    """
    from app.modules.data_sources.registry import provider_registry

    try:
        with Session(target_engine) as session:
            # 1. Seed providers
            for p_meta in provider_registry.list_providers():
                existing = session.scalar(
                    select(DataProviderModel).where(DataProviderModel.id == p_meta.provider_id)
                )
                if not existing:
                    provider_row = DataProviderModel(
                        id=p_meta.provider_id,
                        name=p_meta.name,
                        organization=p_meta.organization,
                        base_url=p_meta.base_url,
                        documentation_url=p_meta.documentation_url,
                        access_method=p_meta.access_method,
                        authentication_required=p_meta.authentication_required,
                        auth_description=p_meta.auth_description,
                        status=p_meta.status,
                        supported_formats=p_meta.supported_formats,
                        rate_limits_info=p_meta.rate_limits_info,
                        licence_info=p_meta.licence_info,
                    )
                    session.add(provider_row)
                    logger.info(f"Seeded data provider: {p_meta.provider_id}")

            # 2. Seed datasets
            for d_meta in provider_registry.list_datasets():
                existing_ds = session.scalar(
                    select(DatasetRegistryModel).where(DatasetRegistryModel.id == d_meta.dataset_id)
                )
                if not existing_ds:
                    ds_row = DatasetRegistryModel(
                        id=d_meta.dataset_id,
                        provider=d_meta.provider_id,
                        product_id=d_meta.product_id,
                        dataset_id=d_meta.dataset_id,
                        dataset_version=None,
                        dataset_part="default",
                        product_title=d_meta.product_title,
                        dataset_description=d_meta.dataset_description,
                        available_variables=d_meta.available_variables,
                        variable_metadata=d_meta.variable_metadata,
                        temporal_resolution=d_meta.temporal_resolution,
                        spatial_resolution=d_meta.spatial_resolution,
                        data_type=d_meta.data_type,
                        spatial_coverage=d_meta.spatial_coverage,
                        depth_levels_count=d_meta.depth_levels_count,
                        depth_min=d_meta.depth_min,
                        depth_max=d_meta.depth_max,
                        source_documentation=d_meta.source_documentation,
                        licence_information=d_meta.licence_information,
                        verification_status=d_meta.verification_status,
                    )
                    session.add(ds_row)
                    logger.info(f"Seeded dataset definition: {d_meta.dataset_id} ({d_meta.provider_id})")

            session.commit()
            logger.info("Provider and dataset registry seeding completed successfully.")
    except Exception as exc:
        logger.warning(f"Could not seed providers and datasets: {exc}")


def init_db(target_engine: Engine = engine) -> None:
    """
    Creates database tables if they do not already exist.
    Never drops or modifies existing tables.
    """
    try:
        logger.info("Initializing database tables (checkfirst=True)...")
        Base.metadata.create_all(bind=target_engine, checkfirst=True)
        logger.info("Database tables verified/initialized successfully.")
        seed_providers_and_datasets(target_engine)
    except Exception as exc:
        logger.warning(f"Database initialization could not complete: {exc}")
        raise
