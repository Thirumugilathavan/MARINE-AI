from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings
from app.database.connection import engine
from app.database.init_db import init_db
from app.storage.s3_client import test_storage_connection
from app.api.routes.marine_data import router as marine_data_router

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