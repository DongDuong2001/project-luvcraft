from pydantic import BaseModel, Field

class KeywordInfo(BaseModel):
    keyword: str
    count: int
    rank: int

class KeywordExtractRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw text to extract keywords from")

class KeywordExtractResponse(BaseModel):
    keywords: list[KeywordInfo]
