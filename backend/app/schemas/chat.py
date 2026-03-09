from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=10)
    category_id: str | None = None


class ChatSource(BaseModel):
    article_id: str
    title: str | None
    score: float | None


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
    used_context: bool
