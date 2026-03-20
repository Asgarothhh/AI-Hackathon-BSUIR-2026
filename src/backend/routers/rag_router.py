import os
import re
import logging
import warnings
from io import BytesIO
from typing import Any
from uuid import uuid4
from collections import Counter

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from sqlalchemy.orm import Session

from src.backend.core.database import get_db
from src.backend.models.comparison_models import Comparison, ComparisonFile, ChangeItem, Report, Document
from src.backend.routers.files import _save_file_and_create_doc
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
logger = logging.getLogger(__name__)


def _read_uploaded_text(upload: UploadFile) -> str:
    filename = (upload.filename or "").strip()
    suffix = os.path.splitext(filename)[1].lower()
    upload.file.seek(0)
    raw = upload.file.read()
    if not raw:
        return ""
    if suffix in {".txt", ".md", ".markdown"}:
        return raw.decode("utf-8", errors="ignore").strip()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadWarning
        except Exception as exc:
            raise HTTPException(status_code=503, detail="PDF parsing requires pypdf") from exc
        warnings.filterwarnings("ignore", category=PdfReadWarning)
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        reader = PdfReader(BytesIO(raw), strict=False)
        pages = []
        for page in list(reader.pages)[:80]:
            pages.append((page.extract_text() or "").strip())
        return "\n\n".join([p for p in pages if p]).strip()
    raise HTTPException(status_code=400, detail=f"Unsupported file format: {suffix or 'unknown'}")


def _split_sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[\.\!\?])\s+|\n+", (text or "").strip())
    out: list[str] = []
    for sentence in raw:
        s = sentence.strip()
        if len(s) >= 35:
            out.append(s)
    return out


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-zа-яё0-9\s]", " ", (text or "").lower(), flags=re.I)).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split(" ") if len(t) >= 3}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return inter / union


def _best_pairs(removed: list[str], added: list[str], *, max_pairs: int = 40) -> list[tuple[str, str, float]]:
    removed_pool = [(r, _tokens(r)) for r in removed]
    added_pool = [(a, _tokens(a)) for a in added]
    used_added: set[int] = set()
    pairs: list[tuple[str, str, float]] = []

    for r_text, r_tokens in removed_pool:
        best_idx = -1
        best_score = 0.0
        for idx, (a_text, a_tokens) in enumerate(added_pool):
            if idx in used_added:
                continue
            score = _jaccard(r_tokens, a_tokens)
            if score > best_score:
                best_score = score
                best_idx = idx
        # Threshold keeps only meaningful "changed from -> to" pairs.
        if best_idx != -1 and best_score >= 0.16:
            used_added.add(best_idx)
            pairs.append((r_text, added_pool[best_idx][0], best_score))
            if len(pairs) >= max_pairs:
                break

    # Add unpaired removed/added rows (still useful for audit).
    if len(pairs) < max_pairs:
        for r_text, _ in removed_pool:
            if any(r_text == p[0] for p in pairs):
                continue
            pairs.append((r_text, "—", 0.0))
            if len(pairs) >= max_pairs:
                break
    if len(pairs) < max_pairs:
        for idx, (a_text, _) in enumerate(added_pool):
            if idx in used_added:
                continue
            pairs.append(("—", a_text, 0.0))
            if len(pairs) >= max_pairs:
                break
    return pairs


def _simple_compare_report(old_text: str, new_text: str, *, old_name: str, new_name: str) -> tuple[str, list[dict]]:
    old_sentences = _split_sentences(old_text)
    new_sentences = _split_sentences(new_text)
    old_counter = Counter(_normalize(s) for s in old_sentences if _normalize(s))
    new_counter = Counter(_normalize(s) for s in new_sentences if _normalize(s))
    kept_count = sum((old_counter & new_counter).values())

    removed: list[str] = []
    added: list[str] = []
    for sentence in old_sentences:
        key = _normalize(sentence)
        if not key:
            continue
        if new_counter.get(key, 0) > 0:
            new_counter[key] -= 1
        else:
            removed.append(sentence)
    # rebuild for additions to preserve new doc order
    old_counter = Counter(_normalize(s) for s in old_sentences if _normalize(s))
    for sentence in new_sentences:
        key = _normalize(sentence)
        if not key:
            continue
        if old_counter.get(key, 0) > 0:
            old_counter[key] -= 1
        else:
            added.append(sentence)

    lines = [
        "# Отчет об анализе изменений НПА",
        "",
        f"Старый файл: {old_name}",
        f"Новый файл: {new_name}",
        "",
        "| Пункт | Было | Стало | Риск | Рекомендация | Ссылка |",
        "|-------|------|-------|------|--------------|--------|",
    ]
    pairs = _best_pairs(removed, added, max_pairs=40)
    if not pairs:
        pairs = [("—", "—", 0.0)]
    
    analysis_items = []
    for idx, (was_text, became_text, score) in enumerate(pairs, start=1):
        rec = (
            "Проверить вручную: найдено вероятное соответствие фрагментов."
            if score >= 0.16
            else "Проверить вручную: фрагмент без надежной пары."
        )
        lines.append(
            f"| {idx} | {was_text} | {became_text} | ⚪ unknown | {rec} | Нет |"
        )
        analysis_items.append({
            "section_id": str(idx),
            "was_text": was_text,
            "became_text": became_text,
            "risk_level": "unknown",
            "comment": rec,
            "portal_link": None
        })

    lines += [
        "",
        f"_Совпадающих фрагментов: {kept_count}; удалено: {len(removed)}; добавлено: {len(added)}._",
    ]

    return "\n".join(lines).strip(), analysis_items


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
    db: Session = Depends(get_db),
) -> RagCompareResponse:
    # 1. Save files to DB as Documents
    try:
        old_doc = await _save_file_and_create_doc(old_file, db)
        new_doc = await _save_file_and_create_doc(new_file, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save files: {exc}")

    # 2. Extract text for analysis (since UploadFile cursor was moved during saving, we might need to read from storage or seek)
    # Actually _save_file_and_create_doc seeks to 0 at the start but might end at the end.
    # We should have used the text before saving or seek again.
    # Re-reading after saving to ensure we have the full content.
    from src.backend.core.storage import get_file_path
    old_text = _read_uploaded_text(old_file)
    new_text = _read_uploaded_text(new_file)

    if not old_text or not new_text:
        raise HTTPException(status_code=400, detail="One or both files are empty after processing")

    # 3. Create Comparison record
    comp = Comparison(
        title=f"RAG: {old_doc.filename} vs {new_doc.filename}",
        status="processing",
        options={"rag": True}
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)

    # 4. Link files
    db.add(ComparisonFile(comparison_id=comp.id, document_id=old_doc.id, role="old"))
    db.add(ComparisonFile(comparison_id=comp.id, document_id=new_doc.id, role="new"))
    db.commit()

    report_markdown = ""
    analysis_items = []

    try:
        from src.rag.agents.graph import analyze_documents
        report_markdown, analysis_results = await analyze_documents(old_text, new_text)
        
        # Convert AnalyzedSection objects to dicts for easier processing
        for item in analysis_results:
            for change in item.changes:
                # If multiple risks per section, we create multiple ChangeItems or consolidate.
                # Following simple logic: one ChangeItem per risk.
                risks = item.risks if item.risks else [None]
                for risk in risks:
                    analysis_items.append({
                        "section_id": item.section_id,
                        "before": change.was_text,
                        "after": change.became_text,
                        "risk_level": risk.risk_level if risk else "unknown",
                        "comment": risk.comment if risk else "No specific risk comment.",
                        "linked_law": {
                            "act": risk.violated_act if risk else None,
                            "ref": risk.article_ref if risk else None,
                            "link": risk.portal_link if risk else None
                        }
                    })
    except Exception as exc:
        logger.warning("RAG compare LLM analyzer failed, using local fallback: %s", exc)
        report_markdown, analysis_items = _simple_compare_report(
            old_text,
            new_text,
            old_name=old_file.filename or "old_file",
            new_name=new_file.filename or "new_file",
        )
        # For fallback, mapping simplified items
        # _simple_compare_report already returns a list of dicts with matching keys.
        pass

    if not report_markdown:
        report_markdown = "Отчет не сформирован."

    # 5. Save ChangeItems to DB
    for item in analysis_items:
        # User request: skip if no "author" (linked_law items are "Отсутствует")
        ll = item.get("linked_law")
        if ll:
            act = str(ll.get("act") or "").strip().lower()
            ref = str(ll.get("ref") or "").strip().lower()
            # If both act and ref are missing or placeholders, skip saving
            if (not act or "отсутствует" in act) and (not ref or "отсутствует" in ref):
                continue

        db.add(ChangeItem(
            comparison_id=comp.id,
            before=item.get("was_text") or item.get("before"),
            after=item.get("became_text") or item.get("after"),
            risk_level=item.get("risk_level"),
            recommendation=item.get("comment"),
            linked_law=item.get("linked_law"),
            kind="rag_analysis"
        ))

    # 6. Finalize Comparison and Report
    report_db = Report(comparison_id=comp.id, status="completed")
    db.add(report_db)
    db.commit()
    db.refresh(report_db)

    comp.status = "completed"
    comp.report_id = report_db.id
    db.add(comp)
    db.commit()

    return RagCompareResponse(
        old_file=old_file.filename or "old_file",
        new_file=new_file.filename or "new_file",
        report_markdown=report_markdown,
    )

