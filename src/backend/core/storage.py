from pathlib import Path
from uuid import uuid4
from typing import Tuple
from fastapi import UploadFile
import os

STORAGE_ROOT = Path(os.getenv("FILE_STORAGE_PATH", "storage"))
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/markdown",
    "text/plain"
}

MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_BYTES", 50 * 1024 * 1024))

def _safe_filename(filename: str) -> str:
    ext = Path(filename).suffix or ""
    return f"{uuid4().hex}{ext}"

def save_upload_file_from_uploadfile(upload_file: UploadFile, filename: str) -> Tuple[str, int]:
    dest_name = _safe_filename(filename)
    dest = STORAGE_ROOT / dest_name
    upload_file.file.seek(0)
    with open(dest, "wb") as out_f:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            out_f.write(chunk)
    size = dest.stat().st_size
    return str(dest_name), size

def get_file_path(rel_path: str) -> str:
    return str((STORAGE_ROOT / rel_path).resolve())
