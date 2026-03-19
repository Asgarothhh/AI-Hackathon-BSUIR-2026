# backend/routers/files.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.core.database import get_db
from backend.core.storage import save_upload_file_from_uploadfile, ALLOWED_MIMES, MAX_FILE_SIZE
from backend.models.comparison_models import Document
from backend.schemas.comparison import UploadResponse
# optional: если хотите сохранять user_id при наличии токена
try:
    from backend.routers.auth import get_current_user
except Exception:
    get_current_user = None

router = APIRouter(prefix="/api/v1/files", tags=["files"])

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_files(
    files: List[UploadFile] = File(...),            # <- ожидаем multipart поле "files"
    db: Session = Depends(get_db),
    # если хотите опционально извлечь user, замените на: user: Optional[User] = Depends(get_current_user) и импорт User
):
    """
    Принимает multipart/form-data с полем files (можно несколько).
    Поддерживаемые форматы: .doc, .docx, .md, .pdf, .txt.
    Доступно без обязательной авторизации (если хотите — добавьте get_current_user).
    """
    saved = []
    for up in files:
        content_type = (up.content_type or "").lower()
        # проверка mime/расширения
        if content_type not in ALLOWED_MIMES:
            ext = (up.filename or "").lower().split(".")[-1] if up.filename else ""
            if ext not in ("doc", "docx", "md", "pdf", "txt"):
                raise HTTPException(status_code=415, detail=f"Unsupported file type: {content_type} / .{ext}")

        # проверка размера (SpooledTemporaryFile)
        try:
            up.file.seek(0, 2)
            size = up.file.tell()
            up.file.seek(0)
        except Exception:
            size = 0

        if size and size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large")

        rel_path, saved_size = save_upload_file_from_uploadfile(up, up.filename or "file")
        doc = Document(
            user_id=None,
            filename=up.filename or "file",
            mime=content_type or "application/octet-stream",
            size=saved_size,
            storage_path=rel_path
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        saved.append(doc)
    return UploadResponse(files=saved)
