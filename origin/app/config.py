from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://cdn:cdn@localhost:5432/cdn"

    s3_bucket: str = "cdn-files"
    s3_region: str = "us-east-1"
    # Set to a MinIO endpoint for local dev (e.g. http://minio:9000). Leave unset for real AWS S3.
    s3_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # Purge fan-out to edges on delete/update
    purge_timeout_seconds: float = 5.0


settings = Settings()
