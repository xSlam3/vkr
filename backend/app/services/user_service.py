from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    @staticmethod
    def create_user(db: Session, user_data: UserCreate) -> User:
        existing_user = UserRepository.get_by_username(db, user_data.username)
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already exists")

        user = User(
            username=user_data.username,
            password_hash=hash_password(user_data.password),
            role=UserRole(user_data.role),
        )
        return UserRepository.create(db, user)

    @staticmethod
    def authenticate(db: Session, username: str, password: str) -> User:
        user = UserRepository.get_by_username(db, username)
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return user

    @staticmethod
    def list_users(db: Session) -> list[User]:
        return UserRepository.list_all(db)

    @staticmethod
    def delete_user(db: Session, user_id: str) -> None:
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        UserRepository.delete(db, user)

    @staticmethod
    def update_user(db: Session, user_id: str, payload: UserUpdate) -> User:
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if payload.username is not None:
            existing = UserRepository.get_by_username(db, payload.username)
            if existing and existing.id != user_id:
                raise HTTPException(status_code=400, detail="Username already exists")
            user.username = payload.username

        if payload.role is not None:
            user.role = UserRole(payload.role)

        if payload.password is not None and payload.password.strip():
            user.password_hash = hash_password(payload.password)

        return UserRepository.update(db, user)
