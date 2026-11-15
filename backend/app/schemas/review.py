from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FacilityReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str) -> str:
        return value.strip()


class FacilityReviewPublicRead(BaseModel):
    id: int
    facility_id: int
    rating: int
    comment: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class FacilityReviewRead(FacilityReviewPublicRead):
    booking_id: int


class FacilityReviewSummary(BaseModel):
    average_rating: float | None
    ratings_count: int
    reviews: list[FacilityReviewPublicRead]
