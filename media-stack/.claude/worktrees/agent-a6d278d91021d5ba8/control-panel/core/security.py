"""Session auth for the evolved control-panel backend. Additive to, not a
replacement for, app.py's verify_same_origin Host-header check (fixed
under /cso, commit e360961) - that check stays in place through the
phased migration and CSRF protection still depends on it; this module
adds a real login on top of it, per Phase 1's "Mirror" note in
.claude/plans/evolved-control-panel-backend.plan.md.
"""
import hashlib
import os

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from core.db import get_db
from models.api_key import ApiKey
from models.user import User

SESSION_COOKIE_NAME = "cp_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 days

_hasher = PasswordHasher()


def _secret_key() -> str:
    key = os.environ.get("CONTROL_PANEL_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "CONTROL_PANEL_SECRET_KEY must be set - see docker-compose.yml's "
            "control-panel environment block"
        )
    return key


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_secret_key(), salt="cp-session")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_session_token(user_id: int) -> str:
    return _serializer().dumps({"user_id": user_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _lookup_api_key(db: Session, raw_key: str) -> ApiKey | None:
    return db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(raw_key)).first()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Requires a real logged-in session. Use for every mutating route."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        user_id = read_session_token(token)
        if user_id is not None:
            user = db.query(User).filter(User.id == user_id).first()
            if user is not None:
                return user
    raise HTTPException(status_code=401, detail="Not authenticated")


def current_user_or_service(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Accepts either a session cookie or an X-Api-Key header. The
    recurring health-check cron and stack-* scripts can't do an
    interactive login, so a valid service API key is an accepted
    alternative on:
      1. every read-only route, and
      2. a documented, bounded set of automation-invoked mutating routes -
         Phase 3 extended the contract for these after finding
         stack-queue-autofix.fish's 5-minute unattended loop (and its
         sibling unstick/rss-sync/search/blocklist/manual-import actions)
         has no way to hold an interactive session. Each router that uses
         this dependency on a mutating route must say so in a comment next
         to the route, same as services/arr/router.py does.
    Callers are responsible for NOT using this dependency on any mutating
    route that isn't part of that documented automation set - those still
    require current_user. Returns the User for a session, or None for a
    valid service key."""
    api_key = request.headers.get("X-Api-Key")
    if api_key:
        key_row = _lookup_api_key(db, api_key)
        if key_row is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return None
    return current_user(request, db)
