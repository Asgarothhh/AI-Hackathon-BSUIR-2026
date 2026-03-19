# backend/routers/auth.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from datetime import timezone

from backend.core.database import get_db
from backend.models.user import User
from backend.models.rbac import Role, RefreshToken, user_roles
from backend.schemas.auth import UserCreate, UserOut, Token, RoleAssignIn
from backend.core.security import create_access_token, create_refresh_token, decode_token, is_refresh_token, ACCESS_TOKEN_EXPIRE_MINUTES

from passlib.context import CryptContext

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
bearer = HTTPBearer()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

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
        # назначаем роль user по умолчанию, если есть
        role_user = db.query(Role).filter_by(name="user").first()
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
    return Token(access_token=access, refresh_token=refresh, expires_in=int(ACCESS_TOKEN_EXPIRE_MINUTES*60))

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
        return Token(access_token=access, refresh_token=new_refresh, expires_in=int(ACCESS_TOKEN_EXPIRE_MINUTES*60))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Invalid refresh token")
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
        db.query(RefreshToken).filter(RefreshToken.user_id == user_id).update({"revoked": True})
        db.commit()
        return {"ok": True}
    except Exception:
        logger.exception("Logout failed")
        raise HTTPException(status_code=400, detail="Logout failed")

@router.post("/role/assign")
def assign_role(payload: RoleAssignIn, db: Session = Depends(get_db)):
    role = db.query(Role).filter_by(name=payload.role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    try:
        db.execute(user_roles.insert().values(user_id=payload.user_id, role_id=role.id))
        db.commit()
        return {"ok": True}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Role already assigned")
