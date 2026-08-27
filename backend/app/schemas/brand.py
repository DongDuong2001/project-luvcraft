from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class BrandProfileFields(BaseModel):
    brand_name: str = Field(min_length=1, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    primary_offerings: str | None = None
    target_audience: str | None = None
    positioning_notes: str | None = None
    core_values: str | None = None
    mission: str | None = None
    primary_markets: str | None = None
    brand_tone: str | None = None


class BrandProfileCreate(BrandProfileFields):
    pass


class BrandProfileUpdate(BaseModel):
    brand_name: str | None = Field(default=None, min_length=1, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    primary_offerings: str | None = None
    target_audience: str | None = None
    positioning_notes: str | None = None
    core_values: str | None = None
    mission: str | None = None
    primary_markets: str | None = None
    brand_tone: str | None = None


class BrandProfileResponse(BrandProfileFields):
    brand_id: UUID
    is_complete: bool = False
    missing_required_fields: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def add_completeness(cls, value):
        required = ("brand_name", "primary_offerings", "target_audience", "positioning_notes", "core_values")
        getter = value.get if isinstance(value, dict) else lambda key, default=None: getattr(value, key, default)
        missing = [key for key in required if not str(getter(key, "") or "").strip()]
        return {key: getter(key) for key in BrandProfileFields.model_fields} | {
            "brand_id": getter("brand_id"), "is_complete": not missing, "missing_required_fields": missing
        }
