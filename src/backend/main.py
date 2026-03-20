import logging
import os
from fastapi import FastAPI, WebSocket, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from src.backend.core.database import get_engine, get_sessionmaker
from src.backend.models.base import Base
from src.backend.ws.manager import ws_manager
from src.backend.routers import auth
from src.backend.routers.files import router as files_router
from src.backend.routers.comparisons import router as comparisons_router
from src.backend.routers.reports import router as reports_router
from src.backend.routers import search
from src.backend.routers.kb_router import router as kb_router
from src.backend.routers.rag_router import router as rag_router

load_dotenv()

# Logging configuration
log_level_name = os.getenv("KB_LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger("src").setLevel(log_level)
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

app = FastAPI(
    title="Unified Comparisons & Knowledge Base API",
    description="Combined backend for document comparison and knowledge base management.",
    version="0.2.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(auth.router)
app.include_router(files_router)
app.include_router(comparisons_router)
app.include_router(reports_router)
app.include_router(search.router)
app.include_router(kb_router)
app.include_router(rag_router)

# Mount static files
app.mount("/kb-static", StaticFiles(directory="src/backend/static"), name="kb-static")

# Database initialization
engine = get_engine()
Base.metadata.create_all(bind=engine)

# WebSocket endpoint for real-time comparison updates
@app.websocket("/ws/comparisons/{comparison_id}")
async def ws_comparison(websocket: WebSocket, comparison_id: int, token: str = None):
    # token passed as query param or header — validate via auth dependency if needed
    await ws_manager.connect(comparison_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # echo or ignore; server pushes events via ws_manager.broadcast
            await websocket.send_text("ok")
    except Exception:
        ws_manager.disconnect(comparison_id, websocket)
