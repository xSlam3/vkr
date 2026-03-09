import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


class KnowledgeMediaType(str, enum.Enum):
    photo = "photo"
    video = "video"


class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    text_content = Column(Text, nullable=False)
    media_url = Column(String, nullable=True)
    media_type = Column(Enum(KnowledgeMediaType), nullable=True)
    category_id = Column(String, ForeignKey("categories.id"), nullable=False, index=True)
    last_edited_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
