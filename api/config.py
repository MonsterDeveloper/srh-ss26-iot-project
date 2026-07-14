from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    api_bearer_token: str = Field(min_length=1)
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "srh_iot"
    db_user: str = "srh_iot"
    db_password: str = Field(validation_alias=AliasChoices("DB_PASSWORD", "POSTGRES_PASSWORD"))
    s3_access_key_id: str = Field(validation_alias=AliasChoices("S3_ACCESS_KEY_ID", "RUSTFS_ACCESS_KEY"))
    s3_secret_access_key: str = Field(validation_alias=AliasChoices("S3_SECRET_ACCESS_KEY", "RUSTFS_SECRET_KEY"))
    s3_bucket: str = "recordings"
    s3_region: str = "us-east-1"
    s3_public_endpoint: str
    s3_internal_endpoint: str
    cors_allowed_origins: list[str] | str
    route_distance_m: float = Field(default=14, gt=0)
    presigned_url_ttl_seconds: int = Field(default=900, gt=0)
    extraction_concurrency: int = Field(default=1, ge=1)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def database_url(self) -> str:
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return f"postgresql+psycopg://{user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
