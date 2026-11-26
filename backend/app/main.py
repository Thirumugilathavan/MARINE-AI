from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings
from app.database.connection import engine
from app.database.init_db import init_db
from app.storage.s3_client import test_storage_connection
from app.api.routes.marine_data import router as marine_data_router
from app.api.routes.unified_providers import (
    providers_router,
    ingestions_router,
)
from app.api.routes.gebco import router as gebco_router
from app.api.routes.biodiversity import router as biodiversity_router
from app.api.routes.taxonomy import router as taxonomy_router
from app.api.routes.fisheries import router as fisheries_router
from app.api.routes.catalogue import router as catalogue_router
from app.api.routes.research_files import router as research_files_router
from app.api.routes.edna import router as edna_router
from app.api.routes.media import router as media_router
from app.api.routes.oceanography import router as oceanography_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Safely ensure database tables are initialized if DB is accessible
    try:
        init_db(engine)
    except Exception as exc:
        logger.warning(f"Database table verification deferred: {exc}")
    yield


app = FastAPI(
    title=settings.app_name,
    description="Marine AI and Data Platform API",
    version="0.1.0",
    lifespan=lifespan,
)


# Register API routers
app.include_router(marine_data_router)
app.include_router(providers_router)
app.include_router(ingestions_router)
app.include_router(gebco_router, prefix="/api/v1")
app.include_router(biodiversity_router, prefix="/api/v1")
app.include_router(taxonomy_router, prefix="/api/v1")
app.include_router(fisheries_router, prefix="/api/v1")
app.include_router(catalogue_router, prefix="/api/v1")
app.include_router(research_files_router, prefix="/api/v1")
app.include_router(edna_router, prefix="/api/v1")
app.include_router(media_router, prefix="/api/v1")
app.include_router(oceanography_router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "project": settings.app_name,
        "message": "Marine AI Platform API is running",
        "version": "0.1.0",
    }


@app.get("/health")
def health_check():
    services = {}

    # PostgreSQL health
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        services["postgresql"] = "healthy"

    except Exception:
        services["postgresql"] = "unhealthy"

    # SeaweedFS health
    try:
        test_storage_connection()
        services["seaweedfs"] = "healthy"

    except Exception:
        services["seaweedfs"] = "unhealthy"

    overall_status = (
        "healthy"
        if all(status == "healthy" for status in services.values())
        else "degraded"
    )

    return {
        "status": overall_status,
        "services": services,
    }