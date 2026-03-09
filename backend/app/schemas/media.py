from typing import Literal

from pydantic import BaseModel, Field


class PresignUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=100)
    scope: Literal["onboarding", "knowledge", "avatars", "misc"] = "misc"


class PresignUploadResponse(BaseModel):
    key: str
    object_url: str
    url: str
    fields: dict[str, str]
    expires_in: int


class PresignDownloadResponse(BaseModel):
    key: str
    url: str
    expires_in: int
