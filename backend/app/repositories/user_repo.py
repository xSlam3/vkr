from sqlalchemy.orm import Session
from app.models.user import User


class UserRepository:

    @staticmethod
    def get_by_username(db: Session, username: str):
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def get_by_id(db: Session, user_id: str):
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def create(db: Session, user: User):
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def list_all(db: Session):
        return db.query(User).all()

    @staticmethod
    def delete(db: Session, user: User):
        db.delete(user)
        db.commit()

    @staticmethod
    def count(db: Session) -> int:
        return db.query(User).count()

    @staticmethod
    def update(db: Session, user: User):
        db.commit()
        db.refresh(user)
        return user
