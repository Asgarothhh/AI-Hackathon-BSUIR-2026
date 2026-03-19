# backend/core/security.py
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import jwt

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-prod-please-make-this-longer-than-32-chars")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

def _now_utc():
    return datetime.utcnow()

def _to_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())

def create_access_token(subject: int, extra: Optional[Dict[str, Any]] = None) -> str:
    now = _now_utc()
    exp = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # sub must be a string for PyJWT
    payload = {"sub": str(subject), "exp": _to_timestamp(exp), "type": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def create_refresh_token(subject: int, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    now = _now_utc()
    exp = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(subject), "exp": _to_timestamp(exp), "type": "refresh"}
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return {"token": token, "expires_at": exp}

def decode_token(token: str) -> Dict[str, Any]:
    # decode returns payload with 'sub' as string (because we encoded it as string)
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

def is_access_token(payload: Dict[str, Any]) -> bool:
    return payload.get("type") == "access"

def is_refresh_token(payload: Dict[str, Any]) -> bool:
    return payload.get("type") == "refresh"
