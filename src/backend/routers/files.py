# backend/routers/files.py
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from src.backend.core.database import get_db
from src.backend.core.storage import save_upload_file_from_uploadfile, ALLOWED_MIMES, MAX_FILE_SIZE, get_file_path
from src.backend.models.comparison_models import Document
from src.backend.schemas.comparison import UploadedFileOut

router = APIRouter(prefix="/api/v1/files", tags=["files"])


def _validate_and_get_size(upload: UploadFile) -> int:
    try:
        upload.file.seek(0, 2)
        size = upload.file.tell()
        upload.file.seek(0)
    except Exception:
        size = 0
    return size


def _validate_meta(filename: str, content_type: Optional[str]) -> None:
    ext = Path(filename).suffix.lower().lstrip(".")
    allowed_exts = {"doc", "docx", "md", "pdf", "txt"}
    if (content_type or "").lower() not in ALLOWED_MIMES and ext not in allowed_exts:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {content_type} / .{ext}")


async def _save_file_and_create_doc(upload: UploadFile, db: Session) -> Document:
    filename = upload.filename or "file"
    content_type = (upload.content_type or "").lower()

    _validate_meta(filename, content_type)

    size = _validate_and_get_size(upload)
    if size and size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    try:
        rel_path, saved_size = save_upload_file_from_uploadfile(upload, filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save file")

    try:
        doc = Document(
            user_id=None,
            filename=filename,
            mime=content_type or "application/octet-stream",
            size=saved_size,
            storage_path=rel_path
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
    except Exception:
        db.rollback()
        try:
            p = Path(get_file_path(rel_path))
            if p.exists():
                p.unlink()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Database error while saving file metadata")

    return doc


@router.post("/upload/first", response_model=UploadedFileOut, status_code=status.HTTP_201_CREATED)
async def upload_first(file: UploadFile = File(...), db: Session = Depends(get_db)):
    doc = await _save_file_and_create_doc(file, db)
    return doc


@router.post("/upload/second", response_model=UploadedFileOut, status_code=status.HTTP_201_CREATED)
async def upload_second(file: UploadFile = File(...), db: Session = Depends(get_db)):
    doc = await _save_file_and_create_doc(file, db)
    return doc
