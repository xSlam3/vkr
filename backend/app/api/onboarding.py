from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.models.user import User
from app.schemas.onboarding import (
    OnboardingDayCreate,
    OnboardingDayRead,
    OnboardingDayUpdate,
    OnboardingDayWithProgress,
    OnboardingProgressRead,
)
from app.services.onboarding_service import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/days", response_model=OnboardingDayRead)
def create_day(
    payload: OnboardingDayCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return OnboardingService.create_day(db, payload)


@router.get("/days", response_model=list[OnboardingDayRead])
def list_days(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return OnboardingService.list_days(db)


@router.get("/days/{day_id}", response_model=OnboardingDayRead)
def get_day(
    day_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return OnboardingService.get_day(db, day_id)


@router.put("/days/{day_id}", response_model=OnboardingDayRead)
def update_day(
    day_id: str,
    payload: OnboardingDayUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return OnboardingService.update_day(db, day_id, payload)


@router.delete("/days/{day_id}")
def delete_day(
    day_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    OnboardingService.delete_day(db, day_id)
    return {"message": "Onboarding day deleted"}


@router.post("/days/{day_id}/complete", response_model=OnboardingProgressRead)
def complete_day(
    day_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OnboardingService.complete_day(db, current_user, day_id)


@router.get("/me", response_model=list[OnboardingDayWithProgress])
def get_my_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OnboardingService.get_my_onboarding(db, current_user)
