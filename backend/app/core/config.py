from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    DATABASE_URL: str = (
        "postgresql://postgres:postgres@localhost:5432/luvcraft"  # default fallback value
    )
    # Provide a dedicated setting for migrations if pooler is used for normal app requests
    MIGRATION_DATABASE_URL: Optional[str] = None

    CELERY_BROKER_URL: str = "pyamqp://luvcraft:luvcraft@localhost:5672//"
    CELERY_RESULT_BACKEND: Optional[str] = None
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Task 4 update: YouTube collector configuration for public video metadata collection.
    YOUTUBE_API_KEY: Optional[str] = None
    GITHUB_TOKEN: Optional[str] = None
    YOUTUBE_REGION_CODE: str = "VN"
    YOUTUBE_RELEVANCE_LANGUAGE: str = "vi"
    YOUTUBE_MAX_RESULTS: int = 50
    YOUTUBE_MIN_RECORDS_THRESHOLD: int = 20
    YOUTUBE_TIMEOUT_MAX_RETRIES: int = 3
    YOUTUBE_TIMEOUT_RETRY_DELAY_SECONDS: int = 60

    # Hybrid sentiment defaults to the deterministic local classifier. Enabling
    # the LLM never requires putting a secret in source control.
    SENTIMENT_ENGINE: Literal["lexicon", "hybrid"] = "lexicon"
    GEMINI_API_KEY: Optional[SecretStr] = None
    GEMINI_SENTIMENT_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_SENTIMENT_PROMPT_VERSION: str = "sentiment-gemini-v1"
    GEMINI_SENTIMENT_BATCH_SIZE: int = Field(default=20, ge=1, le=100)
    GEMINI_SENTIMENT_MAX_INPUT_CHARS: int = Field(default=4000, ge=1)
    GEMINI_SENTIMENT_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=1)
    GEMINI_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    GEMINI_MAX_RETRIES: int = Field(default=2, ge=0, le=10)
    GEMINI_SENTIMENT_INPUT_COST_PER_MILLION_USD: Optional[Decimal] = Field(
        default=None,
        ge=0,
    )
    GEMINI_SENTIMENT_OUTPUT_COST_PER_MILLION_USD: Optional[Decimal] = Field(
        default=None,
        ge=0,
    )
    DEBUG_HTTP: bool = False

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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
            origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]

    @field_validator(
        "GEMINI_SENTIMENT_INPUT_COST_PER_MILLION_USD",
        "GEMINI_SENTIMENT_OUTPUT_COST_PER_MILLION_USD",
        mode="before",
    )
    @classmethod
    def empty_cost_is_unconfigured(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_sentiment_cost_rates(self):
        input_rate = self.GEMINI_SENTIMENT_INPUT_COST_PER_MILLION_USD
        output_rate = self.GEMINI_SENTIMENT_OUTPUT_COST_PER_MILLION_USD
        if (input_rate is None) != (output_rate is None):
            raise ValueError(
                "both Gemini sentiment input and output cost rates must be set"
            )
        return self


settings = Settings()
