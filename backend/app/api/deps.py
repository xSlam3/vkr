from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User, UserRole
from app.repositories.user_repo import UserRepository
from app.core.security import decode_access_token
from jose import JWTError


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _auth_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _resolve_user_from_token(db: Session, token: str) -> User:
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise _auth_error()
    except JWTError as exc:
        raise _auth_error() from exc

    user = UserRepository.get_by_id(db, user_id)
    if not user:
        raise _auth_error()
    return user


def _extract_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()

    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token
    return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = _extract_token(request) if request is not None else None
    if not token:
        raise _auth_error()
    return _resolve_user_from_token(db, token)


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    token = _extract_token(request) if request is not None else None
    if token is None:
        return None
    try:
        return _resolve_user_from_token(db, token)
    except HTTPException:
        return None


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
