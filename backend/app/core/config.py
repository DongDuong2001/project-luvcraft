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

    # SerpApi powers genuine Google Trends observations and publicly indexed
    # social-search results. MAX_ATTEMPTS includes the initial request.
    SERPAPI_API_KEY: Optional[SecretStr] = None
    SERPAPI_MAX_RESULTS: int = Field(default=10, ge=1, le=100)
    SERPAPI_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=10.0)
    SERPAPI_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=5)
    SERPAPI_RETRY_INITIAL_DELAY_SECONDS: int = Field(default=5, ge=1)
    SERPAPI_RETRY_MAX_DELAY_SECONDS: int = Field(default=30, ge=1)
    SERPAPI_COLLECTOR_DEADLINE_SECONDS: int = Field(default=120, ge=10, le=180)
    SERPAPI_MAX_REQUESTS_PER_RUN: int = Field(default=5, ge=1, le=5)
    SERPAPI_LOW_QUOTA_THRESHOLD: int = Field(default=10, ge=0)
    SERPAPI_RELATED_QUERIES_ENABLED: bool = True
    SERPAPI_GEO_TRENDS_ENABLED: bool = False
    SERPAPI_GEO_COUNTRIES: str = "VN,US,JP"
    SERPAPI_GEO_RELATED_COUNTRY_LIMIT: int = Field(default=1, ge=0, le=3)

    @property
    def serpapi_geo_countries(self) -> tuple[str, ...]:
        """Validated, de-duplicated ISO-like country codes for geo trends."""
        countries: list[str] = []
        for raw in self.SERPAPI_GEO_COUNTRIES.split(","):
            code = raw.strip().upper()
            if len(code) == 2 and code.isalpha() and code not in countries:
                countries.append(code)
        return tuple(countries[:3])

    # Public RSS/Atom publication ingestion. Feed URLs are configured in the
    # external collectors YAML; no provider credential is required.
    RSS_MAX_RESULTS: int = Field(default=50, ge=1, le=500)
    RSS_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0)
    RSS_MAX_RETRIES: int = Field(default=3, ge=0, le=10)
    RSS_RETRY_DELAY_SECONDS: int = Field(default=30, ge=1)

    # SocialVault Reddit Collector
    SOCIALVAULT_API_KEY: Optional[SecretStr] = None
    SOCIALVAULT_MAX_RESULTS: int = Field(default=50, ge=1, le=500)
    SOCIALVAULT_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0)
    SOCIALVAULT_MAX_RETRIES: int = Field(default=3, ge=0, le=10)
    SOCIALVAULT_RETRY_DELAY_SECONDS: int = Field(default=10, ge=1)


    # Hybrid sentiment defaults to the deterministic local classifier. Enabling
    # the LLM never requires putting a secret in source control.
    SENTIMENT_ENGINE: Literal["lexicon", "hybrid"] = "hybrid"
    GEMINI_API_KEY: Optional[SecretStr] = None
    GEMINI_SENTIMENT_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_SENTIMENT_PROMPT_VERSION: str = "sentiment-gemini-v1"
    GEMINI_SENTIMENT_BATCH_SIZE: int = Field(default=20, ge=1, le=100)
    SENTIMENT_LLM_FALLBACK_THRESHOLD: float = Field(default=0.65, ge=0, le=1)
    GEMINI_SENTIMENT_MAX_INPUT_CHARS: int = Field(default=4000, ge=1)
    GEMINI_SENTIMENT_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=1)
    COMMUNITY_CLASSIFIER_ENGINE: Literal["rules", "hybrid"] = "hybrid"
    GEMINI_COMMUNITY_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_COMMUNITY_PROMPT_VERSION: str = "community-gemini-v2"
    GEMINI_COMMUNITY_BATCH_SIZE: int = Field(default=25, ge=1, le=100)
    GEMINI_COMMUNITY_MAX_INPUT_CHARS: int = Field(default=4000, ge=1)
    GEMINI_COMMUNITY_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=1)
    MOTIVATION_EXTRACTOR_ENGINE: Literal["rules", "hybrid"] = "hybrid"
    GEMINI_MOTIVATION_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_MOTIVATION_PROMPT_VERSION: str = "motivation-gemini-v2"
    GEMINI_MOTIVATION_BATCH_SIZE: int = Field(default=25, ge=1, le=100)
    GEMINI_MOTIVATION_MAX_INPUT_CHARS: int = Field(default=4000, ge=1)
    GEMINI_MOTIVATION_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=1)
    MOTIVATION_CONFIDENCE_THRESHOLD: float = Field(default=0.72, ge=0, le=1)
    TOPIC_EXTRACTOR_ENGINE: Literal["rules", "hybrid"] = "hybrid"
    GEMINI_TOPIC_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_TOPIC_PROMPT_VERSION: str = "subtopics-gemini-v2"
    GEMINI_TOPIC_BATCH_SIZE: int = Field(default=25, ge=1, le=100)
    GEMINI_TOPIC_MAX_INPUT_CHARS: int = Field(default=4000, ge=1)
    GEMINI_TOPIC_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=1)
    TOPIC_CONFIDENCE_THRESHOLD: float = Field(default=0.72, ge=0, le=1)
    TOPIC_MIN_TREND_EVIDENCE: int = Field(default=3, ge=1)
    DEMAND_EXTRACTOR_ENGINE: Literal["rules", "hybrid"] = "hybrid"
    GEMINI_DEMAND_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_DEMAND_PROMPT_VERSION: str = "demand-gemini-v2"
    GEMINI_DEMAND_BATCH_SIZE: int = Field(default=25, ge=1, le=100)
    GEMINI_DEMAND_MAX_INPUT_CHARS: int = Field(default=4000, ge=1)
    GEMINI_DEMAND_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=1)
    DEMAND_CONFIDENCE_THRESHOLD: float = Field(default=.72, ge=0, le=1)
    COLLABORATION_SEMANTIC_ENGINE: Literal["rules", "hybrid"] = "hybrid"
    GEMINI_COLLABORATION_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_COLLABORATION_PROMPT_VERSION: str = "brand-ip-semantic-v2"
    GEMINI_COLLABORATION_MAX_DOCUMENTS: int = Field(default=30, ge=5, le=50)
    GEMINI_COLLABORATION_MAX_INPUT_CHARS: int = Field(default=1200, ge=200, le=4000)
    GEMINI_COLLABORATION_MAX_OUTPUT_TOKENS: int = Field(default=8192, ge=1024)
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
    REPORT_STORAGE_PATH: Path = PROJECT_ROOT / "data" / "reports"

    # Fail-closed application debug flag. Gates developer-only endpoints such as
    # /auth/dev-login. Must be explicitly enabled for local development.
    DEBUG: bool = False

    # Session cookie security. Secure by default so cookies are only sent over
    # HTTPS; override to False for local HTTP development if needed.
    COOKIE_SECURE: bool = True

    # Supabase Auth Configuration
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # Verified users from these domains are provisioned as internal analysts.
    # Administrator access is never assigned automatically.
    INTERNAL_EMAIL_DOMAINS: str = "pluto.studio,projectpluto.studio"
    RBAC_ADMIN_EMAILS: str = ""

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

    @property
    def internal_email_domains(self) -> set[str]:
        return {
            domain.strip().lower().lstrip("@")
            for domain in self.INTERNAL_EMAIL_DOMAINS.split(",")
            if domain.strip()
        }

    @property
    def rbac_admin_emails(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.RBAC_ADMIN_EMAILS.split(",")
            if email.strip()
        }

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
