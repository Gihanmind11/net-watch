from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..database import get_db
from ..security import create_token, decode_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

_ROLE_PERMISSIONS = {
    "admin": ["view", "scan", "manage"],
    "operator": ["view", "scan"],
    "viewer": ["view"],
}


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


def _user_payload(user: models.User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
        "permissions": _ROLE_PERMISSIONS.get(user.role, ["view"]),
    }


def _find_user(db: Session, username: str) -> models.User | None:
    return db.scalar(
        select(models.User).where(func.lower(models.User.username) == username.strip().lower())
    )


def _issue_tokens(user: models.User) -> dict:
    settings = get_settings()
    access = create_token(
        user.username,
        timedelta(minutes=settings.access_token_expire_minutes),
        {"token_type": "access", "role": user.role},
    )
    refresh = create_token(
        user.username,
        timedelta(days=settings.refresh_token_expire_days),
        {"token_type": "refresh"},
    )
    return {"access_token": access, "refresh_token": refresh, "user": _user_payload(user)}


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = _find_user(db, body.username)
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return _issue_tokens(user)


@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    claims = decode_token(body.refresh_token)
    if claims.get("token_type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")
    user = _find_user(db, str(claims.get("sub", "")))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown or inactive user")
    return _issue_tokens(user)


@router.post("/logout")
def logout() -> dict:
    return {"status": "ok"}
