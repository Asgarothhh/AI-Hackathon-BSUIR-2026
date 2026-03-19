# backend/routers/auth.py
import logging
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import func
from passlib.context import CryptContext

from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# Если нужно, можно добавить StreamHandler, но logging.basicConfig в database.py уже настроил вывод.

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__time_cost=2,
    argon2__memory_cost=65536,
    argon2__parallelism=2
)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    # Логируем входные данные (не логируем пароль в явном виде)
    logger.debug("Register attempt payload username=%s", getattr(user_in, "username", None))

    username_norm = user_in.username.strip().lower()
    logger.debug("Normalized username: %s", username_norm)

    # Покажем, что возвращает поиск по username и по email (если поле есть)
    try:
        existing_by_username = db.query(User).filter(func.lower(User.username) == username_norm).first()
    except Exception as e:
        existing_by_username = None
        logger.exception("Error querying by username for %s", username_norm)
    logger.debug("Existing by username: %r", existing_by_username)

    try:
        # если в модели есть поле email, проверим и его
        existing_by_email = db.query(User).filter(func.lower(User.email) == username_norm).first()
    except Exception:
        existing_by_email = None
    logger.debug("Existing by email: %r", existing_by_email)

    new_user = User(username=username_norm, password_hash=hash_password(user_in.password), is_active=True)
    try:
        db.add(new_user)
        db.flush()  # поймать unique constraint раньше commit
        db.commit()
        db.refresh(new_user)
        logger.info("User created id=%s username=%s", new_user.id, new_user.username)
        return new_user
    except IntegrityError as ie:
        db.rollback()
        logger.exception("IntegrityError during register for %s", username_norm)
        # Возвращаем 409 — конфликт (временно оставляем текст)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already registered")
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error during register for %s", username_norm)
        # Временно возвращаем текст ошибки для отладки; после исправления заменить на общее сообщение
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Простой login endpoint для теста
class LoginIn(UserCreate):
    pass

@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    username_norm = payload.username.strip().lower()
    logger.debug("Login attempt for username=%s", username_norm)
    user = db.query(User).filter(func.lower(User.username) == username_norm).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if pwd_context.needs_update(user.password_hash):
        user.password_hash = hash_password(payload.password)
        db.add(user)
        db.commit()
    return {"id": user.id, "username": user.username}
