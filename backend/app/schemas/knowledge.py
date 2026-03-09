from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CategoryUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CategoryRead(BaseModel):
    id: str
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    text_content: str = Field(min_length=1)
    media_url: str | None = None
    media_type: Literal["photo", "video"] | None = None
    category_id: str


class KnowledgeArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    text_content: str | None = Field(default=None, min_length=1)
    media_url: str | None = None
    media_type: Literal["photo", "video"] | None = None
    category_id: str | None = None


class KnowledgeArticleRead(BaseModel):
    id: str
    title: str
    text_content: str
    media_url: str | None
    media_type: str | None
    category_id: str
    last_edited_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
