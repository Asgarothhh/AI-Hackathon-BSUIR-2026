import logging
import os
import warnings
from pathlib import Path
from typing import List


SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
SUPPORTED_EXTENSIONS = SUPPORTED_TEXT_EXTENSIONS.union({".pdf"})


def read_uploaded_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        return _read_pdf(path)
    raise ValueError(f"Unsupported file format: {suffix}")


def list_upload_files(upload_dir: Path, supported_only: bool = True) -> List[Path]:
    if not upload_dir.exists():
        return []
    return sorted(
        [
            p
            for p in upload_dir.rglob("*")
            if p.is_file() and (not supported_only or p.suffix.lower() in SUPPORTED_EXTENSIONS)
        ],
        key=lambda p: str(p).lower(),
    )


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadWarning
    except Exception as exc:
        raise ValueError(
            "PDF reading requires pypdf package. Install with: pip install pypdf"
        ) from exc

    # Corrupted PDFs can spam parser warnings and slow down processing.
    warnings.filterwarnings("ignore", category=PdfReadWarning)
    logging.getLogger("pypdf").setLevel(logging.ERROR)

    reader = PdfReader(str(path), strict=False)
    max_pages = int(os.getenv("KB_PDF_MAX_PAGES", "80"))
    chunks: List[str] = []
    for page in list(reader.pages)[:max_pages]:
        text = page.extract_text() or ""
        chunks.append(text)
    return "\n\n".join(chunks).strip()
