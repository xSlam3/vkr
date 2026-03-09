from datetime import datetime

from sqlalchemy.orm import Session

from app.models.onboarding import OnboardingDay, OnboardingProcess


class OnboardingRepository:
    @staticmethod
    def create_day(db: Session, data: dict) -> OnboardingDay:
        day = OnboardingDay(**data)
        db.add(day)
        db.commit()
        db.refresh(day)
        return day

    @staticmethod
    def get_day_by_id(db: Session, day_id: str) -> OnboardingDay | None:
        return db.query(OnboardingDay).filter(OnboardingDay.id == day_id).first()

    @staticmethod
    def get_day_by_number(db: Session, day_number: int) -> OnboardingDay | None:
        return db.query(OnboardingDay).filter(OnboardingDay.day_number == day_number).first()

    @staticmethod
    def list_days(db: Session) -> list[OnboardingDay]:
        return db.query(OnboardingDay).order_by(OnboardingDay.day_number.asc()).all()

    @staticmethod
    def update_day(db: Session, day: OnboardingDay, data: dict) -> OnboardingDay:
        for key, value in data.items():
            setattr(day, key, value)
        db.commit()
        db.refresh(day)
        return day

    @staticmethod
    def delete_day(db: Session, day: OnboardingDay) -> None:
        db.query(OnboardingProcess).filter(OnboardingProcess.day_id == day.id).delete()
        db.delete(day)
        db.commit()

    @staticmethod
    def get_progress(db: Session, user_id: str, day_id: str) -> OnboardingProcess | None:
        return (
            db.query(OnboardingProcess)
            .filter(OnboardingProcess.user_id == user_id, OnboardingProcess.day_id == day_id)
            .first()
        )

    @staticmethod
    def list_progress_for_user(db: Session, user_id: str) -> list[OnboardingProcess]:
        return db.query(OnboardingProcess).filter(OnboardingProcess.user_id == user_id).all()

    @staticmethod
    def create_progress(
        db: Session,
        user_id: str,
        day_id: str,
        completed: bool,
        completed_at: datetime | None,
    ) -> OnboardingProcess:
        progress = OnboardingProcess(
            user_id=user_id,
            day_id=day_id,
            completed=completed,
            completed_at=completed_at,
        )
        db.add(progress)
        db.commit()
        db.refresh(progress)
        return progress

    @staticmethod
    def update_progress(
        db: Session,
        progress: OnboardingProcess,
        completed: bool,
        completed_at: datetime | None,
    ) -> OnboardingProcess:
        progress.completed = completed
        progress.completed_at = completed_at
        db.commit()
        db.refresh(progress)
        return progress
