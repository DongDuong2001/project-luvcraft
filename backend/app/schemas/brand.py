from uuid import UUID

from pydantic import BaseModel


class BrandProfileResponse(BaseModel):
    brand_id: UUID
    brand_name: str
    industry: str | None

    model_config = {"from_attributes": True}
