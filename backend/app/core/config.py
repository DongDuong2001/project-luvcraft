from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/luvcraft"
    # Provide a dedicated setting for migrations if pooler is used for normal app requests
    MIGRATION_DATABASE_URL: Optional[str] = None
    
    CELERY_BROKER_URL: str = "pyamqp://luvcraft:luvcraft@localhost:5672//"
    CELERY_RESULT_BACKEND: str = "db+postgresql://postgres:postgres@localhost:5432/luvcraft"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    @property
    def get_migration_database_url(self) -> str:
        return self.MIGRATION_DATABASE_URL or self.DATABASE_URL

settings = Settings()
