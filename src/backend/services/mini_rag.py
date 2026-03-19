import logging
import os
import re
from collections import OrderedDict
from typing import Any, AsyncIterator, Tuple, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.models.kb_models import KnowledgePage
from src.backend.services.kb_store import store
from src.rag.agents.llm_call import get_llm


ROLE_CAN_EDIT = {"admin", "editor"}
logger = logging.getLogger(__name__)


def can_edit(role: str) -> bool:
    return role.lower() in ROLE_CAN_EDIT


def answer_question(question: str, source_slug: Optional[str] = None) -> str:
    sources = get_selected_sources(
        question,
        top_candidates=10,
        top_k=3,
        source_slug=source_slug,
    )
    if not sources:
        return (
            "Не нашел ответа в базе знаний. "
            "Сначала наполните базу через POST /kb/build или POST /kb/build/batch."
        )
    llm_answer = _generate_answer_from_sources(question, sources)
    if not llm_answer:
        llm_answer = sources[0]["fallback_answer"]

    answer_lines = [f"Ответ: {llm_answer}"]
    for source in sources:
        answer_lines.append(
            " - SOURCE|"
            f"{_enc(source['title'])}|{_enc(source['chapter'])}|{_enc(source['link'])}|"
            f"{_enc(source['preview'])}|{_enc(source['highlightText'])}"
        )
    return "\n".join(answer_lines)

def get_selected_sources(
    question: str,
    *,
    top_candidates: int = 10,
    top_k: int = 3,
    source_slug: Optional[str] = None,
) -> list[dict[str, Any]]:
    allowed_slugs = {source_slug} if source_slug else None
    # Hybrid retrieval: existing snippet scorer + deterministic text-search tool.
    candidates = store.search_snippets(question, limit=top_candidates, allowed_slugs=allowed_slugs)
    text_hits = _text_search_tool(question, allowed_slugs=allowed_slugs, limit=top_candidates)
    candidates = _merge_candidates(candidates, text_hits, limit=max(top_candidates * 2, top_candidates))
    if not candidates:
        return []

    # Heuristic pre-clean + fallback answer
    prepared = []
    for item in candidates:
        cleaned = _clean_snippet(item.get("snippet", ""))
        if not cleaned:
            continue
        full_excerpt = cleaned[:320].strip()
        full_excerpt = _sanitize_excerpt_prefix(full_excerpt)
        fallback_answer = cleaned[:240].strip() or question[:240]
        prepared.append(
            {
                "slug": item.get("slug", ""),
                "title": item.get("title", "Источник"),
                "chapter": item.get("chapter", "Раздел"),
                "link": f"/kb/{item.get('slug', '')}",
                "cleanedSnippet": cleaned,
                "highlightText": full_excerpt,
                "preview": _short_preview(full_excerpt, words_limit=7),
                "fallback_answer": fallback_answer,
            }
        )

    if not prepared:
        return []

    # LLM rerank to improve "source correctness"
    reranked = _llm_rerank_sources(question, prepared, top_k=max(top_k * 2, top_k))
    validated: list[dict[str, Any]] = []
    for s in reranked:
        resolved = _resolve_highlight_text(s)
        if not resolved:
            continue
        stable = _stable_highlight_phrase(resolved)
        s["highlightText"] = stable
        s["evidenceText"] = resolved
        s["preview"] = _short_preview(stable, words_limit=7)
        validated.append(s)
    # Keep source cards diverse by document slug when possible.
    validated = _prefer_distinct_slugs(validated, top_k=top_k, unique_per_slug=True)
    if len(validated) < top_k:
        for s in prepared:
            if len(validated) >= top_k:
                break
            if s in validated:
                continue
            resolved = _resolve_highlight_text(s)
            if resolved:
                stable = _stable_highlight_phrase(resolved)
                s["highlightText"] = stable
                s["evidenceText"] = resolved
                s["preview"] = _short_preview(stable, words_limit=7)
                validated.append(s)
    validated = _deduplicate_sources(validated)
    validated = _prefer_distinct_slugs(validated, top_k=top_k, unique_per_slug=True)
    return validated[:top_k]


def _merge_candidates(
    primary: list[dict[str, Any]],
    extra: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in list(primary) + list(extra):
        key = (
            str(item.get("slug", "")).strip().lower(),
            _normalize_for_match(str(item.get("snippet", "")).strip()),
        )
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _text_search_tool(
    query: str,
    *,
    allowed_slugs: Optional[set[str]] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Deterministic full-text retrieval helper for mini-RAG.
    Finds exact/near-exact keyword hits directly in KB markdown and returns real excerpts.
    """
    tokens = [t for t in _normalize_for_match(query).split(" ") if len(t) >= 3]
    if not tokens:
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    for page in store.all_pages():
        if allowed_slugs is not None and page.slug not in allowed_slugs:
            continue
        text = page.markdown or ""
        if not text.strip():
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        for para in paragraphs:
            para_norm = _normalize_for_match(para)
            if not para_norm:
                continue
            overlap = sum(1 for tok in tokens if tok in para_norm)
            if overlap <= 0:
                continue
            phrase_bonus = 0
            q_norm = _normalize_for_match(query)
            if q_norm and q_norm in para_norm:
                phrase_bonus = 3
            score = overlap + phrase_bonus
            excerpt = para[:900].strip()
            scored.append(
                (
                    score,
                    {
                        "slug": page.slug,
                        "title": page.title,
                        "chapter": page.chapter,
                        "snippet": excerpt,
                    },
                )
            )

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def validate_sources_for_display(
    sources: list[dict[str, Any]], *, top_k: int = 5
) -> list[dict[str, Any]]:
    """
    Final guard before sending sources to UI:
    keep only sources that resolve to highlightable text on their page.
    """
    valid: list[dict[str, Any]] = []
    for src in sources:
        resolved = _resolve_highlight_text(src)
        if not resolved:
            continue
        src["highlightText"] = _stable_highlight_phrase(resolved)
        src["evidenceText"] = resolved
        src["preview"] = _short_preview(src["highlightText"], words_limit=7)
        valid.append(src)
        if len(valid) >= top_k:
            break
    valid = _deduplicate_sources(valid)
    valid = _prefer_distinct_slugs(valid, top_k=top_k, unique_per_slug=True)
    return valid[:top_k]


def _deduplicate_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for s in items:
        key = (
            str(s.get("slug", "")).strip().lower(),
            _normalize_for_match(str(s.get("highlightText", "")).strip()),
            _normalize_for_match(str(s.get("preview", "")).strip()),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _prefer_distinct_slugs(
    items: list[dict[str, Any]],
    *,
    top_k: int,
    unique_per_slug: bool = False,
) -> list[dict[str, Any]]:
    if not items:
        return []
    by_slug: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for s in items:
        slug = str(s.get("slug", "")).strip()
        by_slug.setdefault(slug, []).append(s)

    out: list[dict[str, Any]] = []
    used_slugs: set[str] = set()
    while len(out) < top_k:
        progressed = False
        for slug in list(by_slug.keys()):
            bucket = by_slug.get(slug) or []
            if not bucket:
                continue
            if unique_per_slug and slug in used_slugs:
                continue
            out.append(bucket.pop(0))
            used_slugs.add(slug)
            progressed = True
            if len(out) >= top_k:
                break
        if not progressed:
            break
    return out


def _llm_rerank_sources(question: str, sources: list[dict[str, Any]], *, top_k: int) -> list[dict[str, Any]]:
    model_name = os.getenv("MINI_RAG_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
    try:
        llm = get_llm(model_name)
        payload = "\n".join(
            [
                f"{i}. title={s['title']}; chapter={s['chapter']}; snippet={s['cleanedSnippet'][:520]}"
                for i, s in enumerate(sources)
            ]
        )
        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Ты ассистент для ранжирования источников. "
                        "Выбери только действительно нужные источники для ответа на вопрос "
                        "(обычно 1-5), избегай дублей одного и того же документа. "
                        "Верни СТРОГО JSON вида: {\"indices\":[...]} без пояснений."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Вопрос: {question}\n\n"
                        f"Кандидаты:\n{payload}\n\n"
                        f"Максимум можно выбрать {top_k} источников."
                    )
                ),
            ]
        )
        raw = str(response.content or "")
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            obj = __import__("json").loads(match.group(0))
            indices = obj.get("indices") or []
            selected = []
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(sources):
                    selected.append(sources[idx])
                if len(selected) >= top_k:
                    break
            # Deduplicate by (link, highlightText) so multiple fragments on same page survive.
            out: list[dict[str, Any]] = []
            seen: set[tuple[str, str]] = set()
            for s in selected:
                key = (s.get("link", ""), s.get("highlightText", ""))
                if key in seen:
                    continue
                seen.add(key)
                out.append(s)
            if out:
                # Fill to top_k if the model returned too few unique fragments.
                if len(out) < top_k:
                    for s in sources:
                        key = (s.get("link", ""), s.get("highlightText", ""))
                        if key in seen:
                            continue
                        out.append(s)
                        seen.add(key)
                        if len(out) >= top_k:
                            break
                return out[:top_k]
    except Exception as exc:
        logger.warning("Mini RAG source rerank failed: %s", exc)

    # Fallback: keep the first top_k candidates in store ranking order.
    return sources[:top_k]


def _generate_answer_from_sources(question: str, sources: list[dict[str, Any]]) -> str:
    context_blocks: list[str] = []
    for idx, source in enumerate(sources, start=1):
        context_blocks.append(
            f"[SOURCE {idx}] title={source['title']}; chapter={source['chapter']}; "
            f"snippet={source['cleanedSnippet'][:700]}"
        )
    context = "\n".join(context_blocks)
    if not context:
        return ""

    model_name = os.getenv("MINI_RAG_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
    try:
        llm = get_llm(model_name)
        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Ты ассистент базы знаний. Ответь на вопрос пользователя по контексту. "
                        "Дай короткий точный ответ 2-5 предложений на русском. "
                        "Разрешен Markdown (в т.ч. таблицы), но не добавляй список источников в тексте. "
                        "Не копируй длинные куски дословно, а перефразируй."
                    )
                ),
                HumanMessage(content=f"Вопрос: {question}\n\nКонтекст:\n{context}"),
            ]
        )
        return re.sub(r"\s+", " ", str(response.content or "").strip())
    except Exception as exc:
        logger.warning("Mini RAG LLM generation failed: %s", exc)
        return ""


def _normalize_for_match(text: str) -> str:
    text = _clean_snippet(text or "")
    text = text.lower()
    text = re.sub(r"[^a-zа-яё0-9\s]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _sanitize_excerpt_prefix(text: str) -> str:
    # Remove leading bullets/punctuation noise that breaks matching.
    text = re.sub(r"^[\s\-–—:;,.]+", "", text or "")
    return text.strip()


def _resolve_highlight_text(source: dict[str, Any]) -> str | None:
    """
    Return a highlight text that can be found on the page,
    otherwise None.
    """
    slug = str(source.get("slug", "")).strip()
    highlight = _sanitize_excerpt_prefix(str(source.get("highlightText", "")).strip())
    if not slug or not highlight:
        return None
    page = store.get(slug)
    if not page or not page.markdown:
        return None

    page_norm = _normalize_for_match(page.markdown)
    if not page_norm:
        return None

    for candidate in _candidate_highlights(highlight):
        cand_norm = _normalize_for_match(candidate)
        if not cand_norm:
            continue
        if cand_norm in page_norm:
            return candidate

    # Fallback: key phrase from first 6 words. We return plain normalized phrase,
    # and UI block-level highlight can still locate the exact paragraph.
    hl_norm = _normalize_for_match(highlight)
    words = [w for w in hl_norm.split(" ") if w]
    key = " ".join(words[:6]).strip()
    if key and key in page_norm:
        return key
    return None


def _candidate_highlights(text: str) -> list[str]:
    """
    Build cleaner candidate phrases from noisy snippet fragments.
    """
    source = _sanitize_excerpt_prefix(text)
    candidates: list[str] = [source]

    # Split common noisy separators from extracted list-like snippets.
    parts = re.split(r"\s-\s|[:;]\s+|\.\s+", source)
    for p in parts:
        p2 = _sanitize_excerpt_prefix(p)
        if len(p2.split()) >= 5:
            candidates.append(p2)

    # De-duplicate while preserving order.
    out: list[str] = []
    seen = set()
    for c in candidates:
        key = c.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c.strip())
    return out


def _stable_highlight_phrase(text: str, words: int = 10) -> str:
    """
    Produce a short punctuation-free phrase that is easier to find in UI.
    """
    norm = _normalize_for_match(text)
    parts = [w for w in norm.split(" ") if w]
    if not parts:
        return _sanitize_excerpt_prefix(text)
    return " ".join(parts[:words]).strip()


async def stream_answer_from_sources(question: str, sources: list[dict[str, Any]]) -> AsyncIterator[str]:
    """
    Stream tokens from OpenRouter via LangChain ChatOpenAI.
    Yields plain text chunks.
    """
    context_blocks: list[str] = []
    for idx, source in enumerate(sources, start=1):
        context_blocks.append(
            f"[SOURCE {idx}] title={source['title']}; chapter={source['chapter']}; "
            f"snippet={source['cleanedSnippet'][:700]}"
        )
    context = "\n".join(context_blocks)
    if not context:
        return

    model_name = os.getenv("MINI_RAG_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
    llm = get_llm(model_name)
    messages = [
        SystemMessage(
            content=(
                "Ты ассистент базы знаний. Ответь на вопрос пользователя по контексту. "
                "Дай короткий точный ответ 2-5 предложений на русском. "
                "Разрешен Markdown (в т.ч. таблицы), но не добавляй список источников в тексте. "
                "Отвечай только текстом."
            )
        ),
        HumanMessage(content=f"Вопрос: {question}\n\nКонтекст:\n{context}"),
    ]
    async for chunk in llm.astream(messages):
        token = getattr(chunk, "content", None)
        if token:
            yield token


def _clean_snippet(text: str) -> str:
    cleaned = text.replace("\n", " ")
    cleaned = re.sub(r"<a id=\"[^\"]+\"></a>", "", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"\[[^\]]+\]\([^)]+\)", "", cleaned)
    cleaned = re.sub(r"[*_~`>|]", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _short_preview(text: str, words_limit: int = 7) -> str:
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words:
        return ""
    if len(words) <= words_limit:
        return " ".join(words)
    return " ".join(words[:words_limit]) + " ..."


def _enc(text: str) -> str:
    from urllib.parse import quote

    return quote(text, safe="")


def rag_with_optional_edit(
    question: str,
    role: str,
    allow_edit: bool,
    target_slug: str | None,
) -> Tuple[str, bool, str | None]:
    normalized_question = question.strip()
    if not normalized_question:
        return "Вопрос пустой. Напишите, что именно нужно найти в базе знаний.", False, None

    answer = answer_question(normalized_question, source_slug=target_slug)
    if not (allow_edit and target_slug and can_edit(role)):
        return answer, False, None

    page: KnowledgePage | None = store.get(target_slug)
    if not page:
        return answer + "\n\nНевозможно применить правку: страница не найдена.", False, None

    # Minimal edit strategy: append Q/A note section to keep traceability.
    page.markdown += (
        "\n\n## RAG Update\n\n"
        f"**Запрос:** {normalized_question}\n\n"
        f"**Ответ:** {answer}\n"
    )
    store.upsert(page)
    return answer + "\n\nПравка страницы применена.", True, page.slug
