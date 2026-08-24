import os

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.db import get_db
from core.rate_limit import rate_limit
from core.security import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
    create_session_token,
    current_user,
    verify_password,
)
from models.audit_log import AuditLog
from models.user import User

# secure=False by default: this stack runs LAN-only with no TLS. Set
# CONTROL_PANEL_SECURE_COOKIE=1 if you ever add a reverse proxy with TLS;
# with secure=True browsers will refuse to send the cookie over HTTP.
_SESSION_SECURE = os.environ.get("CONTROL_PANEL_SECURE_COOKIE", "") == "1"

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Read by main.py's router auto-discovery - not required for the route to
# work, but documents this service for a future fleet/status listing.
SERVICE_META = {"label": "Auth", "health_check": None}


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    _rate: None = Depends(rate_limit(max_requests=5, window_seconds=60)),
):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        db.add(AuditLog(action="login_failed", detail=payload.username))
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_session_token(user.id)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_SESSION_SECURE,
    )
    db.add(AuditLog(user_id=user.id, action="login"))
    db.commit()
    return {"username": user.username}


@router.post("/logout")
def logout(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    response.delete_cookie(SESSION_COOKIE_NAME)
    db.add(AuditLog(user_id=user.id, action="logout"))
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "is_admin": bool(user.is_admin)}
