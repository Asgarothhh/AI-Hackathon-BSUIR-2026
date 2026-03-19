# backend/core/database.py
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Логирование SQLAlchemy
logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:password@localhost:5432/ai_hackathon"
)

# Engine и Session factory
engine = create_engine(DATABASE_URL, future=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

def get_engine():
    return engine

def get_sessionmaker():
    return SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ensure_database_exists():
    """
    DEV helper: всегда вызывает Base.metadata.create_all.
    В production используйте Alembic и уберите/замените этот вызов.
    """
    try:
        # Импорт Base локально, чтобы избежать циклических импортов
        from backend.models.user import Base
    except Exception as e:
        logging.getLogger(__name__).exception("Cannot import Base for ensure_database_exists: %s", e)
        raise

    # Создаём таблицы, описанные в Base.metadata
    Base.metadata.create_all(bind=engine)
    logging.getLogger(__name__).info("Database schema ensured (create_all executed).")
