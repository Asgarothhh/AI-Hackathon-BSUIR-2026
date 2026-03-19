# backend/main.py
import logging
from fastapi import FastAPI
from backend.core.database import ensure_database_exists
from backend.routers import auth

logger = logging.getLogger(__name__)
app = FastAPI(title="AI Hackathon API")

# DEV: гарантируем создание таблиц при старте
try:
    ensure_database_exists()
except Exception:
    logger.exception("Failed to ensure database exists on startup.")
    # не прерываем старт приложения, но логируем

# Подключаем роутеры
app.include_router(auth.router)
