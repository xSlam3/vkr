from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.repositories.onboarding_repo import OnboardingRepository
from app.schemas.onboarding import OnboardingDayCreate, OnboardingDayUpdate, OnboardingDayWithProgress
from app.services.rich_text_service import RichTextService


class OnboardingService:
    @staticmethod
    def create_day(db: Session, payload: OnboardingDayCreate):
        if OnboardingRepository.get_day_by_number(db, payload.day_number):
            raise HTTPException(status_code=400, detail="Day number already exists")
        data = payload.model_dump()
        data["text_content"] = RichTextService.sanitize(data["text_content"])
        return OnboardingRepository.create_day(db, data)

    @staticmethod
    def list_days(db: Session):
        return OnboardingRepository.list_days(db)

    @staticmethod
    def get_day(db: Session, day_id: str):
        day = OnboardingRepository.get_day_by_id(db, day_id)
        if not day:
            raise HTTPException(status_code=404, detail="Onboarding day not found")
        return day

    @staticmethod
    def update_day(db: Session, day_id: str, payload: OnboardingDayUpdate):
        day = OnboardingService.get_day(db, day_id)
        update_data = payload.model_dump(exclude_unset=True)

        new_day_number = update_data.get("day_number")
        if new_day_number is not None and new_day_number != day.day_number:
            existing = OnboardingRepository.get_day_by_number(db, new_day_number)
            if existing:
                raise HTTPException(status_code=400, detail="Day number already exists")

        if "text_content" in update_data:
            update_data["text_content"] = RichTextService.sanitize(update_data["text_content"])

        if not update_data:
            return day
        return OnboardingRepository.update_day(db, day, update_data)

    @staticmethod
    def delete_day(db: Session, day_id: str) -> None:
        day = OnboardingService.get_day(db, day_id)
        OnboardingRepository.delete_day(db, day)

    @staticmethod
    def complete_day(db: Session, current_user: User, day_id: str):
        if current_user.role != UserRole.employee:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only employees can mark onboarding progress",
            )

        OnboardingService.get_day(db, day_id)
        progress = OnboardingRepository.get_progress(db, current_user.id, day_id)
        if progress and progress.completed:
            return progress

        now = datetime.now(timezone.utc)
        if progress:
            return OnboardingRepository.update_progress(db, progress, completed=True, completed_at=now)

        return OnboardingRepository.create_progress(
            db,
            user_id=current_user.id,
            day_id=day_id,
            completed=True,
            completed_at=now,
        )

    @staticmethod
    def get_my_onboarding(db: Session, current_user: User) -> list[OnboardingDayWithProgress]:
        days = OnboardingRepository.list_days(db)
        progress_items = OnboardingRepository.list_progress_for_user(db, current_user.id)
        progress_by_day_id = {item.day_id: item for item in progress_items}

        result: list[OnboardingDayWithProgress] = []
        for day in days:
            progress = progress_by_day_id.get(day.id)
            result.append(
                OnboardingDayWithProgress(
                    id=day.id,
                    day_number=day.day_number,
                    title=day.title,
                    text_content=day.text_content,
                    media_url=day.media_url,
                    media_type=day.media_type.value if day.media_type else None,
                    completed=progress.completed if progress else False,
                    completed_at=progress.completed_at if progress else None,
                )
            )
        return result
