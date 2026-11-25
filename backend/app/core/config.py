from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sstrix Marine AI Platform"
    app_env: str = "development"
    app_debug: bool = True

    # PostgreSQL
    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_name: str = "sstrix_marine"
    database_user: str = "sstrix_admin"
    database_password: str

    # SeaweedFS
    seaweedfs_endpoint: str = "http://127.0.0.1:8333"
    seaweedfs_access_key: str = "sstrix-team"
    seaweedfs_secret_key: str

    # Storage buckets
    seaweedfs_bucket_raw: str = "marine-raw"
    seaweedfs_bucket_curated: str = "marine-curated"
    seaweedfs_bucket_derived: str = "marine-derived"
    seaweedfs_bucket_media: str = "marine-media"
    seaweedfs_bucket_edna: str = "marine-edna"
    seaweedfs_bucket_models: str = "marine-models"
    seaweedfs_bucket_research: str = "marine-research"

    # Copernicus Marine Service Credentials (Optional)
    copernicus_marine_username: str | None = None
    copernicus_marine_password: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()