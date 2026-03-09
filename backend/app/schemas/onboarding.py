from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OnboardingDayCreate(BaseModel):
    day_number: int = Field(ge=1, le=7)
    title: str = Field(min_length=1, max_length=255)
    text_content: str = Field(min_length=1)
    media_url: str | None = None
    media_type: Literal["photo", "video"] | None = None


class OnboardingDayUpdate(BaseModel):
    day_number: int | None = Field(default=None, ge=1, le=7)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    text_content: str | None = Field(default=None, min_length=1)
    media_url: str | None = None
    media_type: Literal["photo", "video"] | None = None


class OnboardingDayRead(BaseModel):
    id: str
    day_number: int
    title: str
    text_content: str
    media_url: str | None
    media_type: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OnboardingProgressRead(BaseModel):
    id: str
    user_id: str
    day_id: str
    completed: bool
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class OnboardingDayWithProgress(BaseModel):
    id: str
    day_number: int
    title: str
    text_content: str
    media_url: str | None
    media_type: str | None
    completed: bool
    completed_at: datetime | None
