from pathlib import Path
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

import json
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates

from src.backend.models.kb_models import KnowledgePage
from src.backend.schemas.kb_schemas import (
    AskRequest,
    BatchBuildKnowledgeBaseRequest,
    BatchBuildKnowledgeBaseResponse,
    BuildFromUploadsRequest,
    BuildKnowledgeBaseRequest,
    BuildKnowledgeBaseResponse,
    PageUpdateRequest,
)
from src.backend.services.kb_store import store
from src.backend.services.markdown_service import render_markdown
from src.backend.services.mini_rag import can_edit
from src.backend.services.mini_rag import (
    get_selected_sources,
    stream_answer_from_sources,
    validate_sources_for_display,
)
from src.backend.services.upload_reader import list_upload_files, read_uploaded_file
from src.rag.agents.kb_builder_agent import KnowledgeBaseBuilderAgent


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BASE_DIR.parents[1]
UPLOADS_DIR = PROJECT_ROOT / "uploads"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(prefix="/kb", tags=["knowledge-base"])
logger = logging.getLogger(__name__)


def _read_documents_parallel(files: list[Path]) -> tuple[list[dict], list[str]]:
    """
    Read uploaded files in parallel to speed up multi-file KB builds.
    """
    if not files:
        return [], []

    workers = max(1, int(os.getenv("KB_UPLOAD_READ_WORKERS", "4")))
    total_files = len(files)
    docs_by_index: dict[int, dict] = {}
    errors: list[str] = []

    def _read_one(idx: int, file_path: Path):
        rel_path = str(file_path.relative_to(UPLOADS_DIR)).replace("\\", "/")
        logger.info("KB uploads read started %s/%s: %s", idx, total_files, rel_path)
        content = read_uploaded_file(file_path)
        return idx, rel_path, content

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_read_one, idx, file_path): (idx, file_path)
            for idx, file_path in enumerate(files, start=1)
        }
        for future in as_completed(futures):
            idx, file_path = futures[future]
            rel_path = str(file_path.relative_to(UPLOADS_DIR)).replace("\\", "/")
            try:
                _, rel_path, content = future.result()
                if not content.strip():
                    errors.append(f"{rel_path}: file is empty after parsing")
                    logger.warning("KB uploads skipped empty %s/%s: %s", idx, total_files, rel_path)
                    continue
                docs_by_index[idx] = {"name": rel_path, "content": content, "path": rel_path}
                logger.info(
                    "KB uploads read done %s/%s: %s (chars=%s)",
                    idx,
                    total_files,
                    rel_path,
                    len(content),
                )
            except Exception as exc:
                errors.append(f"{rel_path}: {exc}")
                logger.warning("KB uploads read error %s/%s: %s (%s)", idx, total_files, rel_path, exc)

    documents = [docs_by_index[i] for i in sorted(docs_by_index.keys())]
    return documents, errors


def _extract_page_chapters(markdown: str) -> list[dict]:
    nav: list[dict] = []
    current_anchor = None
    for line in markdown.splitlines():
        anchor_match = re.search(r'<a id="([^"]+)"></a>', line)
        if anchor_match:
            current_anchor = anchor_match.group(1)

        heading_match = re.match(r"^(#{2,4})\s+(.*)$", line.strip())
        if heading_match:
            heading_level = len(heading_match.group(1))
            heading_text = re.sub(r"<[^>]+>", "", heading_match.group(2)).strip()
            heading_text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading_text)
            heading_text = re.sub(r"\(#def-[^)]+\)", "", heading_text).strip()
            if not heading_text:
                continue
            if heading_text.lower().startswith("навигация по определениям"):
                continue
            if current_anchor and current_anchor.startswith("def-"):
                # Hide service anchors from sidebar.
                current_anchor = None
                continue
            if current_anchor is None:
                current_anchor = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "-", heading_text.lower()).strip("-")
            nav.append({"title": heading_text, "anchor": current_anchor, "level": heading_level})
            current_anchor = None
    return nav


def _prepare_markdown_with_heading_anchors(markdown: str) -> tuple[str, list[dict]]:
    """
    Inject anchors into h2-h4 markdown headings and build sidebar nav.
    This guarantees that sidebar links always point to existing anchors.
    """
    lines = markdown.splitlines()
    new_lines: list[str] = []
    nav: list[dict] = []
    service_titles = {"источники", "изображения", "навигация по определениям"}
    current_chapter = "Обзор"

    for line in lines:
        match = re.match(r"^(#{2,4})\s+(.*)$", line.strip())
        if not match:
            new_lines.append(line)
            continue

        level = len(match.group(1))
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
        title = re.sub(r"\(#def-[^)]+\)", "", title).strip()
        if not title:
            new_lines.append(line)
            continue

        anchor = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "-", title.lower()).strip("-")
        anchor = anchor or f"section-{len(nav)+1}"
        clean_title = title

        new_lines.append(f"{'#' * level} <a id=\"{anchor}\"></a>{clean_title}")
        if clean_title.lower() not in service_titles and not anchor.startswith("def-"):
            if level == 2:
                current_chapter = clean_title
            nav.append(
                {
                    "title": clean_title,
                    "anchor": anchor,
                    "level": level,
                    "chapter": current_chapter,
                }
            )

    if not nav:
        # Fallback so sidebar never stays empty.
        new_lines.insert(0, '<a id="overview"></a>')
        nav.append({"title": "Обзор", "anchor": "overview", "level": 2, "chapter": "Обзор"})

    return "\n".join(new_lines), nav


def _build_sources_meta(sources: list[str]) -> list[dict]:
    out: list[dict] = []
    for source in sources:
        if source.startswith("http://") or source.startswith("https://"):
            out.append(
                {
                    "name": source.split("/")[-1] or source,
                    "url": source,
                    "download_url": source,
                    "is_external": True,
                }
            )
            continue

        path_obj = Path(source)
        filename = path_obj.name if path_obj.name else source
        out.append(
            {
                "name": filename,
                "url": f"/kb/sources/download?name={filename}",
                "download_url": f"/kb/sources/download?name={filename}",
                "is_external": False,
            }
        )
    return out


@router.post("/build", response_model=BuildKnowledgeBaseResponse)
def build_page(payload: BuildKnowledgeBaseRequest) -> BuildKnowledgeBaseResponse:
    logger.info(
        "KB /build started: title='%s', chapter='%s', chars=%s",
        payload.title,
        payload.chapter,
        len(payload.document_text or ""),
    )
    try:
        builder = KnowledgeBaseBuilderAgent()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        extracted = builder.process(payload.title, payload.chapter, payload.document_text)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"KB build failed: {exc}. Проверь OPENROUTER_MODEL/OPENROUTER_FALLBACK_MODEL в .env",
        ) from exc
    markdown = builder.to_markdown(extracted, payload.sources, payload.images)
    page = KnowledgePage(
        slug=extracted["slug"],
        title=payload.title,
        chapter=payload.chapter,
        markdown=markdown,
        sources=payload.sources,
        images=payload.images,
    )
    store.upsert(page, save=False)
    terms = [item.get("term", "").strip() for item in extracted.get("definitions", [])]
    if not store.auto_crosslink_terms(terms, page.slug):
        store.flush()
    logger.info(
        "KB /build finished: slug='%s', definitions=%s",
        page.slug,
        len(terms),
    )

    return BuildKnowledgeBaseResponse(
        slug=page.slug, title=page.title, chapter=page.chapter, markdown=page.markdown
    )


@router.get("/theme/style.css")
def kb_theme_style():
    style_path = BASE_DIR / "templates" / "style.css"
    if not style_path.exists():
        raise HTTPException(status_code=404, detail="Theme style not found")
    return FileResponse(path=str(style_path), media_type="text/css")


@router.post("/build/batch", response_model=BatchBuildKnowledgeBaseResponse)
def build_pages_batch(payload: BatchBuildKnowledgeBaseRequest) -> BatchBuildKnowledgeBaseResponse:
    logger.info("KB /build/batch started: pages=%s", len(payload.pages or []))
    try:
        builder = KnowledgeBaseBuilderAgent()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    built: list[BuildKnowledgeBaseResponse] = []
    total = len(payload.pages)
    for idx, item in enumerate(payload.pages, start=1):
        logger.info("KB /build/batch page started %s/%s: title='%s'", idx, total, item.title)
        try:
            extracted = builder.process(item.title, item.chapter, item.document_text)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"KB batch build failed on '{item.title}': {exc}",
            ) from exc
        markdown = builder.to_markdown(extracted, item.sources, item.images)
        page = KnowledgePage(
            slug=extracted["slug"],
            title=item.title,
            chapter=item.chapter,
            markdown=markdown,
            sources=item.sources,
            images=item.images,
        )
        store.upsert(page, save=False)
        terms = [definition.get("term", "").strip() for definition in extracted.get("definitions", [])]
        if not store.auto_crosslink_terms(terms, page.slug):
            store.flush()
        logger.info("KB /build/batch page done %s/%s: slug='%s'", idx, total, page.slug)

        built.append(
            BuildKnowledgeBaseResponse(
                slug=page.slug,
                title=page.title,
                chapter=page.chapter,
                markdown=page.markdown,
            )
        )

    logger.info("KB /build/batch finished: built=%s", len(built))
    return BatchBuildKnowledgeBaseResponse(pages=built)


@router.get("/uploads/files")
def list_files_from_uploads() -> dict:
    files = [str(path.relative_to(UPLOADS_DIR)).replace("\\", "/") for path in list_upload_files(UPLOADS_DIR, supported_only=False)]
    return {"upload_dir": str(UPLOADS_DIR), "files": files}


@router.post("/build/from-uploads/stream")
def build_pages_from_uploads_stream(payload: BuildFromUploadsRequest) -> StreamingResponse:
    """
    NDJSON stream for long-running KB build from uploads.
    Emits progress events and final result:
    - {"type":"progress","stage":"...","...":...}
    - {"type":"result","pages":[...],"errors":[...]}
    - {"type":"done"}
    """

    async def gen():
        request_started = perf_counter()
        logger.info(
            "KB /build/from-uploads/stream started: combine=%s, requested_files=%s",
            payload.combine_into_single_page,
            len(payload.file_names or []),
        )
        def emit_progress(stage: str, **extra):
            msg = {"type": "progress", "stage": stage, **extra}
            return json.dumps(msg, ensure_ascii=False) + "\n"

        try:
            builder = KnowledgeBaseBuilderAgent()
        except ValueError as exc:
            yield json.dumps({"type": "error", "detail": str(exc)}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
            return

        yield emit_progress("started")
        files = list_upload_files(UPLOADS_DIR)
        if payload.file_names:
            allowed = {name.strip().replace("\\", "/") for name in payload.file_names if name.strip()}
            files = [
                path
                for path in files
                if (
                    path.name in allowed
                    or str(path.relative_to(UPLOADS_DIR)).replace("\\", "/") in allowed
                )
            ]

        if not files:
            yield json.dumps(
                {"type": "error", "detail": "No supported files found in uploads folder"},
                ensure_ascii=False,
            ) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
            return

        yield emit_progress("files_selected", total_files=len(files))
        logger.info("KB stream files selected: total=%s", len(files))
        built: list[BuildKnowledgeBaseResponse] = []
        read_started = perf_counter()
        documents, errors = _read_documents_parallel(files)
        for idx, doc in enumerate(documents, start=1):
            yield emit_progress("file_loaded", index=idx, total=len(files), file=doc["path"])
        read_ms = int((perf_counter() - read_started) * 1000)
        logger.info(
            "KB stream files read done: loaded=%s/%s, errors=%s, took_ms=%s",
            len(documents),
            len(files),
            len(errors),
            read_ms,
        )

        if not documents:
            yield json.dumps(
                {"type": "error", "detail": "Failed to parse selected upload files. " + "; ".join(errors[:5])},
                ensure_ascii=False,
            ) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
            return

        if payload.combine_into_single_page:
            merged_title = (payload.combined_title or "").strip()
            if not merged_title:
                merged_preview = "\n\n".join(doc["content"][:3000] for doc in documents[:3])
                merged_title = builder.suggest_title(
                    merged_preview,
                    fallback=f"Сводная база знаний ({len(documents)} файлов)",
                )
            chunk_size_chars = int(os.getenv("KB_CHUNK_SIZE_CHARS", "18000"))
            chunks = builder._chunk_documents(documents, chunk_size_chars=chunk_size_chars)
            yield emit_progress(
                "chunking_ready",
                title=merged_title,
                documents=len(documents),
                total_chunks=len(chunks),
            )
            logger.info(
                "KB stream chunking: title='%s', documents=%s, chunks=%s",
                merged_title,
                len(documents),
                len(chunks),
            )

            try:
                chunk_partials: list[dict] = []
                workers = max(1, int(os.getenv("KB_CHUNK_WORKERS", "3")))
                futures = {}
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    for chunk_idx, chunk in enumerate(chunks, start=1):
                        chunk_title = f"{merged_title} (часть {chunk_idx})"
                        futures[
                            executor.submit(builder.process, chunk_title, payload.chapter, chunk["content"])
                        ] = (chunk_idx, chunk.get("name", ""))
                        yield emit_progress(
                            "chunk_started",
                            index=chunk_idx,
                            total=len(chunks),
                            chunk_name=chunk.get("name", ""),
                        )

                    partials_by_idx: dict[int, dict] = {}
                    for future in as_completed(futures):
                        chunk_idx, chunk_name = futures[future]
                        extracted_part = future.result()
                        partials_by_idx[chunk_idx] = extracted_part
                        logger.info(
                            "KB stream processing chunk done %s/%s: %s",
                            chunk_idx,
                            len(chunks),
                            chunk_name,
                        )
                        yield emit_progress(
                            "chunk_done",
                            index=chunk_idx,
                            total=len(chunks),
                            chunk_name=chunk_name,
                        )
                chunk_partials = [partials_by_idx[i] for i in sorted(partials_by_idx.keys())]
                extracted = builder._merge_extractions(chunk_partials, merged_title, payload.chapter)
                yield emit_progress("chunks_merged", total_chunks=len(chunks))
                merged_sources = [doc["path"] for doc in documents]
                markdown = builder.to_markdown(extracted, merged_sources, [])
                markdown = builder.enrich_created_markdown(
                    title=merged_title,
                    chapter=payload.chapter,
                    markdown=markdown,
                    chunk_results=chunk_partials,
                )
                page = KnowledgePage(
                    slug=extracted["slug"],
                    title=merged_title,
                    chapter=payload.chapter,
                    markdown=markdown,
                    sources=merged_sources,
                    images=[],
                )
                store.upsert(page, save=False)
                terms = [definition.get("term", "").strip() for definition in extracted.get("definitions", [])]
                if not store.auto_crosslink_terms(terms, page.slug):
                    store.flush()
                built.append(
                    BuildKnowledgeBaseResponse(
                        slug=page.slug,
                        title=page.title,
                        chapter=page.chapter,
                        markdown=page.markdown,
                    )
                )
                yield emit_progress("page_saved", slug=page.slug, title=page.title)
                logger.info("KB stream page saved: slug='%s'", page.slug)
            except Exception as exc:
                yield json.dumps(
                    {"type": "error", "detail": f"KB combined build failed: {exc}"},
                    ensure_ascii=False,
                ) + "\n"
                yield json.dumps({"type": "done"}) + "\n"
                return
        else:
            for idx, doc in enumerate(documents, start=1):
                try:
                    yield emit_progress("doc_build_started", index=idx, total=len(documents), file=doc["name"])
                    title = builder.suggest_title(doc["content"], fallback=Path(doc["name"]).stem)
                    extracted = builder.process(title, payload.chapter, doc["content"])
                    markdown = builder.to_markdown(extracted, [doc["path"]], [])
                    page = KnowledgePage(
                        slug=extracted["slug"],
                        title=title,
                        chapter=payload.chapter,
                        markdown=markdown,
                        sources=[doc["path"]],
                        images=[],
                    )
                    store.upsert(page, save=False)
                    terms = [definition.get("term", "").strip() for definition in extracted.get("definitions", [])]
                    if not store.auto_crosslink_terms(terms, page.slug):
                        store.flush()
                    built.append(
                        BuildKnowledgeBaseResponse(
                            slug=page.slug,
                            title=page.title,
                            chapter=page.chapter,
                            markdown=page.markdown,
                        )
                    )
                    yield emit_progress("doc_build_done", index=idx, total=len(documents), slug=page.slug)
                    logger.info("KB stream per-doc build done %s/%s: slug='%s'", idx, len(documents), page.slug)
                except Exception as exc:
                    errors.append(f"{doc['name']}: {exc}")
                    yield emit_progress("doc_build_error", index=idx, total=len(documents), file=doc["name"], detail=str(exc))
                    logger.warning("KB stream per-doc build error %s/%s: %s (%s)", idx, len(documents), doc["name"], exc)

        if not built:
            yield json.dumps(
                {"type": "error", "detail": "Failed to build pages from uploads. " + "; ".join(errors[:5])},
                ensure_ascii=False,
            ) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
            return

        yield json.dumps(
            {
                "type": "result",
                "pages": [page.model_dump() for page in built],
                "errors": errors,
            },
            ensure_ascii=False,
        ) + "\n"
        yield json.dumps({"type": "done"}) + "\n"
        total_ms = int((perf_counter() - request_started) * 1000)
        logger.info(
            "KB /build/from-uploads/stream finished: built=%s, errors=%s, took_ms=%s",
            len(built),
            len(errors),
            total_ms,
        )

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.get("/sources/download")
def download_source(name: str):
    safe_name = Path(name).name
    file_path = UPLOADS_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Source file not found")
    return FileResponse(path=str(file_path), filename=safe_name, media_type="application/octet-stream")


@router.get("/{slug}", response_class=HTMLResponse)
def kb_page(request: Request, slug: str, x_user_role: str = Header(default="viewer")) -> HTMLResponse:
    page = store.get(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    prepared_markdown, chapter_nav = _prepare_markdown_with_heading_anchors(page.markdown)
    html = render_markdown(prepared_markdown)
    return templates.TemplateResponse(
        request,
        "kb.html",
        {
            "page": page,
            "html": html,
            "chapter_nav": chapter_nav,
            "sources_meta": _build_sources_meta(page.sources),
            "can_edit": can_edit(x_user_role),
            "user_role": x_user_role,
        },
    )


@router.get("/", response_class=HTMLResponse)
def kb_index(request: Request, x_user_role: str = Header(default="viewer")) -> HTMLResponse:
    pages = store.all_pages()
    if not pages:
        welcome = KnowledgePage(
            slug="welcome",
            title="Welcome",
            chapter="General",
            markdown="# Welcome\n\nБаза знаний пуста. Сначала создайте страницу через POST /kb/build.",
        )
        store.upsert(welcome)
        pages = [welcome]
    non_welcome = [p for p in pages if p.slug != "welcome"]
    first = non_welcome[0] if non_welcome else pages[0]
    prepared_markdown, chapter_nav = _prepare_markdown_with_heading_anchors(first.markdown)
    html = render_markdown(prepared_markdown)
    return templates.TemplateResponse(
        request,
        "kb.html",
        {
            "page": first,
            "html": html,
            "chapter_nav": chapter_nav,
            "sources_meta": _build_sources_meta(first.sources),
            "can_edit": can_edit(x_user_role),
            "user_role": x_user_role,
        },
    )

@router.patch("/{slug}")
def update_page(slug: str, payload: PageUpdateRequest, x_user_role: str = Header(default="viewer")) -> dict:
    if not can_edit(x_user_role):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    page = store.get(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    page.markdown = payload.markdown
    store.upsert(page)
    return {"status": "ok", "slug": slug}


@router.post("/ask/stream")
def ask_rag_stream(payload: AskRequest, x_user_role: str = Header(default="viewer")) -> StreamingResponse:
    """
    NDJSON stream:
    - {"type":"token","value":"..."}
    - {"type":"meta","answer":"...","sources":[...],"edited":bool,"edited_slug":...}
    - {"type":"done"}
    """

    async def gen():
        question = (payload.question or "").strip()
        if not question:
            yield json.dumps({"type": "error", "detail": "Вопрос пустой"}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
            return

        sources = get_selected_sources(question, top_candidates=12, top_k=3)
        if not sources:
            answer = (
                "Не нашел ответа в базе знаний. "
                "Сначала наполните базу через POST /kb/build или POST /kb/build/batch."
            )
            yield json.dumps({"type": "token", "value": answer}) + "\n"
            yield json.dumps({"type": "meta", "answer": answer, "sources": [], "edited": False, "edited_slug": None}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
            return

        allow_edit = bool(payload.allow_edit and payload.target_slug and can_edit(x_user_role))

        answer_text = ""
        try:
            async for token in stream_answer_from_sources(question, sources):
                answer_text += token
                yield json.dumps({"type": "token", "value": token}, ensure_ascii=False) + "\n"
        except Exception as exc:
            logger = __import__("logging").getLogger(__name__)
            logger.warning("Mini RAG stream failed: %s", exc)
            # Fallback answer
            answer_text = sources[0]["fallback_answer"]
            yield json.dumps({"type": "token", "value": answer_text}, ensure_ascii=False) + "\n"

        # Cleanup answer formatting
        answer_text = re.sub(r"\s+", " ", answer_text).strip()

        edited = False
        edited_slug = None
        if allow_edit and payload.target_slug:
            page = store.get(payload.target_slug)
            if page:
                page.markdown += (
                    "\n\n## RAG Update\n\n"
                    f"**Запрос:** {question}\n\n"
                    f"**Ответ:** {answer_text}\n"
                )
                store.upsert(page)
                edited = True
                edited_slug = page.slug

        # Final safety filter: only truly highlightable sources go to UI.
        safe_sources = validate_sources_for_display(sources, top_k=3)
        out_sources = [
            {
                "title": s["title"],
                "chapter": s["chapter"],
                "link": s["link"],
                "preview": s["preview"],
                "highlightText": s["highlightText"],
            }
            for s in safe_sources
        ]

        yield json.dumps(
            {"type": "meta", "answer": answer_text, "sources": out_sources, "edited": edited, "edited_slug": edited_slug},
            ensure_ascii=False,
        ) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")
