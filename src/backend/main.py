import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from src.backend.routers.kb_router import router as kb_router

load_dotenv()

log_level_name = os.getenv("KB_LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger("src").setLevel(log_level)


app = FastAPI(
    title="Knowledge Base Service",
    description="Knowledge base web app connected to the main FastAPI site.",
    version="0.1.0",
)

app.include_router(kb_router)
app.mount("/kb-static", StaticFiles(directory="src/backend/static"), name="kb-static")

