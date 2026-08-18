from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..config import get_settings
from ..security import create_token, decode_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


def _user_payload(username: str) -> dict:
    return {"id": 1, "username": username, "role": "admin", "permissions": ["view", "scan", "manage"]}


def _issue_tokens(username: str) -> dict:
    settings = get_settings()
    access = create_token(
        username,
        timedelta(minutes=settings.access_token_expire_minutes),
        {"token_type": "access"},
    )
    refresh = create_token(
        username,
        timedelta(days=settings.refresh_token_expire_days),
        {"token_type": "refresh"},
    )
    return {"access_token": access, "refresh_token": refresh, "user": _user_payload(username)}


@router.post("/login")
def login(body: LoginRequest):
    settings = get_settings()
    if body.username != settings.demo_user or body.password != settings.demo_password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return _issue_tokens(body.username)


@router.post("/refresh")
def refresh(body: RefreshRequest):
    claims = decode_token(body.refresh_token)
    if claims.get("token_type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")
    return _issue_tokens(claims["sub"])


@router.post("/logout")
def logout() -> dict:
    return {"status": "ok"}
