import os
import re
from io import BytesIO
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.backend.schemas.rag_schemas import (
    RagAskRequest,
    RagAskResponse,
    RagCompareResponse,
    RagHealthResponse,
    RagHit,
    RagIndexBuildRequest,
    RagRetrieveRequest,
    RagRetrieveResponse,
)
from src.backend.services.kb_store import store
from src.backend.services.mini_rag import (
    get_selected_sources,
    stream_answer_from_sources,
    validate_sources_for_display,
)
from src.rag.agents.llm_call import get_llm

router = APIRouter(prefix="/rag", tags=["rag"])


def _read_uploaded_text(upload: UploadFile) -> str:
    filename = (upload.filename or "").strip()
    suffix = os.path.splitext(filename)[1].lower()
    raw = upload.file.read()
    if not raw:
        return ""
    if suffix in {".txt", ".md", ".markdown"}:
        return raw.decode("utf-8", errors="ignore").strip()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise HTTPException(status_code=503, detail="PDF parsing requires pypdf") from exc
        reader = PdfReader(BytesIO(raw), strict=False)
        pages = []
        for page in list(reader.pages)[:80]:
            pages.append((page.extract_text() or "").strip())
        return "\n\n".join([p for p in pages if p]).strip()
    raise HTTPException(status_code=400, detail=f"Unsupported file format: {suffix or 'unknown'}")


def _split_with_overlap(text: str, chunk_size: int, overlap: int) -> list[str]:
    clean = (text or "").strip()
    if not clean:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph
        if len(current) > chunk_size:
            for idx in range(0, len(current), chunk_size):
                chunks.append(current[idx : idx + chunk_size].strip())
            current = ""
    if current:
        chunks.append(current)

    if overlap <= 0 or len(chunks) <= 1:
        return chunks

    overlapped: list[str] = [chunks[0]]
    for idx in range(1, len(chunks)):
        prev = chunks[idx - 1]
        tail = prev[-overlap:] if len(prev) > overlap else prev
        overlapped.append(f"{tail}\n{chunks[idx]}".strip())
    return overlapped


def _safe_hits(question: str, top_candidates: int, top_k: int) -> list[dict[str, Any]]:
    sources = get_selected_sources(question, top_candidates=top_candidates, top_k=top_k)
    safe_sources = validate_sources_for_display(sources, top_k=top_k)
    return [
        {
            "title": s["title"],
            "chapter": s["chapter"],
            "link": s["link"],
            "preview": s["preview"],
            "highlightText": s["highlightText"],
        }
        for s in safe_sources
    ]


@router.get("/health", response_model=RagHealthResponse)
def rag_health() -> RagHealthResponse:
    llm_ok = bool(os.getenv("OPENROUTER_API_KEY"))
    vector_ok = False
    vector_error = None
    try:
        from src.rag.vectorstore.store import vector_store  # noqa: F401

        vector_ok = True
    except Exception as exc:  # pragma: no cover - diagnostic endpoint
        vector_error = str(exc)

    kb_pages = len(store.all_pages())
    return RagHealthResponse(
        ok=llm_ok and kb_pages >= 0,
        llm={"ok": llm_ok, "model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")},
        vector_store={"ok": vector_ok, "backend": "supabase", "error": vector_error},
        kb={"ok": True, "pages": kb_pages},
    )


@router.post("/retrieve", response_model=RagRetrieveResponse)
def rag_retrieve(payload: RagRetrieveRequest) -> RagRetrieveResponse:
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is empty")

    hits = _safe_hits(query, payload.top_candidates, payload.top_k)
    return RagRetrieveResponse(query=query, hits=[RagHit(**hit) for hit in hits])


@router.post("/ask", response_model=RagAskResponse)
async def rag_ask(payload: RagAskRequest) -> RagAskResponse:
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is empty")

    sources = get_selected_sources(question, top_candidates=payload.top_candidates, top_k=payload.top_k)
    if not sources:
        return RagAskResponse(
            answer=(
                "Не нашел ответа в базе знаний. "
                "Сначала наполните базу через POST /kb/build или POST /kb/build/batch."
            ),
            sources=[],
        )

    answer_text = ""
    try:
        async for token in stream_answer_from_sources(question, sources):
            answer_text += token
    except Exception:
        answer_text = sources[0]["fallback_answer"]
    answer_text = re.sub(r"\s+", " ", answer_text).strip()
    out_sources = _safe_hits(question, payload.top_candidates, payload.top_k)
    return RagAskResponse(answer=answer_text, sources=[RagHit(**hit) for hit in out_sources])


@router.post("/index/build")
def rag_build_index(payload: RagIndexBuildRequest) -> dict:
    pages = store.all_pages()
    if payload.page_slugs:
        allowed = set(payload.page_slugs)
        pages = [p for p in pages if p.slug in allowed]
    if not pages:
        raise HTTPException(status_code=404, detail="No pages found for indexing")

    try:
        from src.rag.vectorstore.store import vector_store
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Vector store unavailable: {exc}") from exc

    texts: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []
    for page in pages:
        chunks = _split_with_overlap(page.markdown, payload.chunk_size, payload.chunk_overlap)
        for idx, chunk in enumerate(chunks):
            texts.append(chunk)
            metadatas.append(
                {
                    "slug": page.slug,
                    "title": page.title,
                    "chapter": page.chapter,
                    "chunk_index": idx,
                }
            )
            ids.append(f"{page.slug}:{idx}:{uuid4().hex[:8]}")

    if not texts:
        raise HTTPException(status_code=400, detail="No text chunks produced")

    try:
        vector_store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
    except TypeError:
        # Some vector store backends may not support custom ids.
        vector_store.add_texts(texts=texts, metadatas=metadatas)

    # Warm-up check to detect obvious config issues right away.
    get_llm()

    return {
        "status": "ok",
        "indexed_pages": len(pages),
        "indexed_chunks": len(texts),
        "chunk_size": payload.chunk_size,
        "chunk_overlap": payload.chunk_overlap,
        "reset_index": payload.reset_index,
    }


@router.post("/compare/upload", response_model=RagCompareResponse)
async def rag_compare_upload(
    old_file: UploadFile = File(...),
    new_file: UploadFile = File(...),
) -> RagCompareResponse:
    old_text = _read_uploaded_text(old_file)
    new_text = _read_uploaded_text(new_file)
    if not old_text:
        raise HTTPException(status_code=400, detail="old_file is empty after parsing")
    if not new_text:
        raise HTTPException(status_code=400, detail="new_file is empty after parsing")

    try:
        from src.rag.agents.graph import analyzer_model
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Analyzer model unavailable: {exc}") from exc

    try:
        result = await analyzer_model.ainvoke(
            {
                "old_doc_text": old_text,
                "new_doc_text": new_text,
                "completed_analysis": [],
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"RAG compare failed: {exc}") from exc

    report = ""
    if isinstance(result, dict):
        report = str((result.get("final_report_metadata") or {}).get("text") or "").strip()
    if not report:
        report = "Отчет не сформирован."

    return RagCompareResponse(
        old_file=old_file.filename or "old_file",
        new_file=new_file.filename or "new_file",
        report_markdown=report,
    )

