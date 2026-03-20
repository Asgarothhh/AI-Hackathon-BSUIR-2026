import logging
from typing import Callable
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from backend.core.database import get_db
from backend.models.user import User
from backend.models.rbac import Role as RoleModel, Permission, RefreshToken, user_roles, role_permissions
from backend.schemas.auth import UserCreate, UserOut, Token, RoleAssignIn
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    is_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from passlib.context import CryptContext

import jwt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
bearer = HTTPBearer()


# --- password helpers ---
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --- auth helpers / dependencies ---
def _raise_401(detail: str = "Could not validate credentials"):
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        _raise_401("Token expired")
    except Exception:
        _raise_401("Invalid token")

    if payload.get("type") != "access":
        _raise_401("Invalid token type")

    sub = payload.get("sub")
    if sub is None:
        _raise_401("Token missing subject")
    try:
        user_id = int(sub)
    except ValueError:
        _raise_401("Invalid subject in token")

    user = db.query(User).get(user_id)
    if not user:
        _raise_401("User not found")
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")
    return user


# --- permission check helper ---
def user_has_permission(db: Session, user: User, permission_name: str) -> bool:
    role_rows = db.execute(user_roles.select().where(user_roles.c.user_id == user.id)).fetchall()
    role_ids = [r.role_id for r in role_rows]
    if not role_ids:
        return False
    perm = db.query(Permission).filter(Permission.name == permission_name).first()
    if not perm:
        return False
    rp = db.execute(
        role_permissions.select().where(
            (role_permissions.c.role_id.in_(role_ids)) & (role_permissions.c.permission_id == perm.id)
        )
    ).first()
    return rp is not None


def require_permission(permission_name: str) -> Callable:
    def _dep(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        if not user_has_permission(db, user, permission_name):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return True

    return _dep


# --- endpoints ---
@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    email_norm = payload.email.strip().lower()
    existing = db.query(User).filter(func.lower(User.email) == email_norm).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    new_user = User(email=email_norm, password_hash=hash_password(payload.password), is_active=True)
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        role_user = db.query(RoleModel).filter_by(name="user").first()
        if role_user:
            db.execute(user_roles.insert().values(user_id=new_user.id, role_id=role_user.id))
            db.commit()
        return new_user
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conflict during registration")
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error during register")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/login", response_model=Token)
def login(payload: UserCreate, db: Session = Depends(get_db)):
    email_norm = payload.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email_norm).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access = create_access_token(subject=user.id)
    refresh_data = create_refresh_token(subject=user.id)
    refresh = refresh_data["token"]
    expires_at = refresh_data["expires_at"]
    rt = RefreshToken(user_id=user.id, token=refresh, expires_at=expires_at)
    db.add(rt)
    db.commit()
    return Token(access_token=access, refresh_token=refresh, expires_in=int(ACCESS_TOKEN_EXPIRE_MINUTES * 60))


@router.post("/token/refresh", response_model=Token)
def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = decode_token(token)
        if not is_refresh_token(payload):
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = int(payload.get("sub"))
        rt = db.query(RefreshToken).filter_by(token=token, user_id=user_id, revoked=False).first()
        if not rt:
            raise HTTPException(status_code=401, detail="Refresh token revoked or not found")
        access = create_access_token(subject=user_id)
        new_refresh_data = create_refresh_token(subject=user_id)
        new_refresh = new_refresh_data["token"]
        new_expires_at = new_refresh_data["expires_at"]
        rt.token = new_refresh
        rt.expires_at = new_expires_at
        db.add(rt)
        db.commit()
        return Token(access_token=access, refresh_token=new_refresh, expires_in=int(ACCESS_TOKEN_EXPIRE_MINUTES * 60))
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        logger.exception("Invalid refresh token")
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        logger.exception("Logout failed: invalid token")
        raise HTTPException(status_code=400, detail="Invalid token")

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=400, detail="Token missing subject")
    try:
        user_id = int(sub)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid subject in token")

    if payload.get("type") == "refresh":
        db.query(RefreshToken).filter(RefreshToken.token == token, RefreshToken.user_id == user_id).update({"revoked": True})
    else:
        db.query(RefreshToken).filter(RefreshToken.user_id == user_id).update({"revoked": True})
    db.commit()
    return {"ok": True}


@router.post("/role/assign")
def assign_role(
    payload: RoleAssignIn,
    db: Session = Depends(get_db),
    _admin: bool = Depends(require_permission("manage:roles")),
):
    role = db.query(RoleModel).filter_by(name=payload.role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    try:
        db.execute(user_roles.insert().values(user_id=payload.user_id, role_id=role.id))
        db.commit()
        return {"ok": True}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Role already assigned")
