# backend/main.py
import os
from fastapi import FastAPI, WebSocket, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.core.database import get_engine, get_sessionmaker
from backend.models.base import Base
from backend.ws.manager import ws_manager
from backend.routers import auth  # ваш модуль аутентификации
from backend.routers.files import router as files_router
from backend.routers.comparisons import router as comparisons_router
from backend.routers.reports import router as reports_router

app = FastAPI(title="Comparisons API")

# CORS — настройте домены фронта
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include routers
app.include_router(auth.router)
app.include_router(files_router)
app.include_router(comparisons_router)
app.include_router(reports_router)

# create tables in dev if needed
engine = get_engine()
Base.metadata.create_all(bind=engine)

# WebSocket endpoint
@app.websocket("/ws/comparisons/{comparison_id}")
async def ws_comparison(websocket: WebSocket, comparison_id: int, token: str = None):
    # token passed as query param or header — validate via auth dependency if needed
    # For simplicity: accept connection; in prod validate JWT
    await ws_manager.connect(comparison_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # echo or ignore; server pushes events via ws_manager.broadcast
            await websocket.send_text("ok")
    except Exception:
        ws_manager.disconnect(comparison_id, websocket)
