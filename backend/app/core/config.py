from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/luvcraft" # default fallback value
    # Provide a dedicated setting for migrations if pooler is used for normal app requests
    MIGRATION_DATABASE_URL: Optional[str] = None

    CELERY_BROKER_URL: str = "pyamqp://luvcraft:luvcraft@localhost:5672//"
    CELERY_RESULT_BACKEND: Optional[str] = None
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Task 4 update: YouTube collector configuration for public video metadata collection.
    YOUTUBE_API_KEY: Optional[str] = None
    YOUTUBE_REGION_CODE: str = "VN"
    YOUTUBE_RELEVANCE_LANGUAGE: str = "vi"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def get_migration_database_url(self) -> str:
        return self.MIGRATION_DATABASE_URL or self.DATABASE_URL

    @property
    def celery_result_backend_url(self) -> str:
        # Follow DATABASE_URL by default so Docker/Supabase overrides also apply to Celery.
        return self.CELERY_RESULT_BACKEND or f"db+{self.DATABASE_URL}"

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]


settings = Settings()
