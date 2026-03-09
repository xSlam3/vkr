import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class MediaType(str, enum.Enum):
    photo = "photo"
    video = "video"


class OnboardingDay(Base):
    __tablename__ = "onboarding_days"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    day_number = Column(Integer, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    text_content = Column(Text, nullable=False)
    media_url = Column(String, nullable=True)
    media_type = Column(Enum(MediaType), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OnboardingProcess(Base):
    __tablename__ = "onboarding_processes"
    __table_args__ = (UniqueConstraint("user_id", "day_id", name="uq_onboarding_process_user_day"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    day_id = Column(String, ForeignKey("onboarding_days.id"), nullable=False, index=True)
    completed = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
