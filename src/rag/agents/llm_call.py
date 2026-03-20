import os
import logging
import re

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.constants import Send
from langchain_openai import ChatOpenAI

from src.rag.agents import states
from src.rag.agents.llm import planner, analyst_llm
from src.rag.tools.web_search import search_sources, TRUSTED_LEGAL_DOMAINS

load_dotenv()
logger = logging.getLogger(__name__)


def get_llm(model_name: str | None = None) -> ChatOpenAI:
    """
    Shared LLM factory for all modules that need direct model calls.
    """
    resolved_model = (
        model_name
        or os.getenv("OPENROUTER_MODEL")
        or os.getenv("MINI_RAG_MODEL")
        or "openai/gpt-4o-mini"
    )
    return ChatOpenAI(
        model=resolved_model,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
    )


# def orchestrator(state: states.State):
#     """
#     Оркестратор: анализирует структуру документов и разбивает их на
#     логические пары (статьи/пункты) для детального анализа.
#     """
#
#     prompt = """Ты — ведущий юрист-аналитик. Твоя задача:
#         1. Сопоставить старую и новую редакции документа.
#         2. Разбить их на список статей/пунктов.
#         3. Для каждой пары определить, есть ли изменения.
#         Верни список объектов AnalyzedSection с заполненными ID и исходными текстами.
#     """
#
#     response = planner.invoke([
#         SystemMessage(content=prompt),
#         HumanMessage(content=f"Старая редакция: {state['old_doc_text']}\n\nНовая редакция: {state['new_doc_text']}")
#     ])
#
#     return {"sections_to_analyze": response.sections}

async def orchestrator(state: states.State):
    prompt = (
        "Разбей документы на логические пары пунктов. Не анализируй риски. "
        "Верни только ключевые измененные пункты (максимум 40). "
        "Ответ должен быть кратким и строго структурированным."
    )
    old_doc = _clip_for_planner(state.get("old_doc_text", ""))
    new_doc = _clip_for_planner(state.get("new_doc_text", ""))

    # Deterministic path for large documents to avoid structured-output overflow.
    if len(old_doc) + len(new_doc) > 12000:
        full_sections = _build_sections_without_llm(old_doc, new_doc, max_sections=40)
        logger.info("Orchestrator (fallback) создал %s секций для анализа", len(full_sections))
        return {"sections_to_analyze": full_sections}

    try:
        response = await planner.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=f"Old: {old_doc}\nNew: {new_doc}")
        ])

        # ПРЕВРАЩАЕМ легкие модели в твои тяжелые AnalyzedSection
        full_sections = []
        for s in response.sections:
            full_sections.append(states.AnalyzedSection(
                section_id=s.section_id,
                changes=[states.LegalChange(
                    was_text=s.old_text,
                    became_text=s.new_text,
                    change_type="semantic",
                    meaning_diff="Pending analysis..."
                )],
                risks=[]
            ))
    except Exception as exc:
        logger.warning("Planner failed in orchestrator, using deterministic fallback: %s", exc)
        full_sections = _build_sections_without_llm(old_doc, new_doc, max_sections=40)

    logger.info("Orchestrator создал %s секций для анализа", len(full_sections))
    return {"sections_to_analyze": full_sections[:40]}


async def worker(state: states.WorkerState):
    """
    Воркер: Проводит глубокий семантический анализ конкретного пункта
    и проверяет его на риски противоречия законодательству РБ.
    """
    section = state["section"]

    prompt = f"""Проведи юридическую экспертизу пункта {section.section_id}.
    1. Выяви семантические изменения (например, замена прав на обязанности, изменение сроков).
    2. Оцени соответствие иерархии НПА Беларуси (Конституция -> Законы -> Указы).
    3. Определи уровень риска (green/yellow/red) и дай рекомендацию.
    """

    # Воркер возвращает заполненный объект AnalyzedSection
    analysis = await analyst_llm.ainvoke([
        SystemMessage(content=prompt),
        HumanMessage(content=f"Анализируемый фрагмент: {section.model_dump()}")
    ])

    # Привязываем portal_link к реальному поиску, а не к "додуманным" URL модели.
    for risk in analysis.risks:
        query_parts = [
            (risk.violated_act or "").strip(),
            (risk.article_ref or "").strip(),
            "Республика Беларусь",
        ]
        query = " ".join([p for p in query_parts if p])
        if not query:
            continue

        sources = search_sources(
            query=query,
            limit=3,
            preferred_domains=TRUSTED_LEGAL_DOMAINS,
        )
        if sources:
            risk.portal_link = sources[0].url

    return {"completed_analysis": [analysis]}


def syntheziser(state: states.State):
    """
    Синтезатор: Собирает все проверенные статьи в финальную таблицу-отчет.
    """
    results = state["completed_analysis"]

    # Формируем Markdown-таблицу согласно требованиям:
    # «было → стало → статья закона → уровень риска → рекомендация»
    report_lines = ["# Отчет об анализе изменений НПА\n", "| Пункт | Было | Стало | Риск | Рекомендация | Ссылка |",
                    "|-------|------|-------|------|--------------|--------|"]

    for item in results:
        for change in item.changes:
            for risk in item.risks:
                # Цветовая маркировка (эмуляция для Markdown/Docx)
                risk_emoji = {"red": "🔴", "yellow": "🟡", "green": "🟢"}.get(risk.risk_level, "⚪")
                link_md = f"[Link]({risk.portal_link})" if risk.portal_link else "Нет"

                line = (f"| {item.section_id} | {change.was_text} | {change.became_text} | "
                        f"{risk_emoji} {risk.risk_level} | {risk.comment} | {link_md} |")
                report_lines.append(line)

    return {"final_report_metadata": {"text": "\n".join(report_lines)}}


def assign_analysts(state: states.State):
    """Создает воркера для каждой найденной секции"""
    return [Send("worker", {"section": s, "hierarchy_level": "All"})
            for s in state["sections_to_analyze"]
    ]


def _clip_for_planner(text: str, max_chars: int = 8000) -> str:
    """
    Protect orchestrator from context overflow on large files.
    Keeps start+end where legal changes often live.
    """
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    if len(clean) <= max_chars:
        return clean
    head = clean[: max_chars // 2]
    tail = clean[-(max_chars // 2) :]
    return head + "\n\n...[TRUNCATED]...\n\n" + tail


def _split_legal_chunks(text: str, chunk_chars: int = 700) -> list[str]:
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    if not clean:
        return []
    # Prefer legal boundaries first.
    parts = re.split(r"(?=(?:статья|пункт|глава|раздел)\s+\d+)", clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        # fallback by sentence windows
        sentences = re.split(r"(?<=[\.\!\?;])\s+", clean)
        parts = []
        current = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            candidate = (current + " " + sent).strip() if current else sent
            if len(candidate) > chunk_chars and current:
                parts.append(current)
                current = sent
            else:
                current = candidate
        if current:
            parts.append(current)
    return parts


def _build_sections_without_llm(old_doc: str, new_doc: str, max_sections: int = 40) -> list[states.AnalyzedSection]:
    old_parts = _split_legal_chunks(old_doc)
    new_parts = _split_legal_chunks(new_doc)
    total = max(len(old_parts), len(new_parts), 1)
    out: list[states.AnalyzedSection] = []
    for idx in range(total):
        old_text = old_parts[idx] if idx < len(old_parts) else ""
        new_text = new_parts[idx] if idx < len(new_parts) else ""
        if not old_text and not new_text:
            continue
        if _normalize_for_compare(old_text) == _normalize_for_compare(new_text):
            continue
        out.append(
            states.AnalyzedSection(
                section_id=f"sec-{idx + 1}",
                changes=[
                    states.LegalChange(
                        was_text=old_text[:1200],
                        became_text=new_text[:1200],
                        change_type="semantic",
                        meaning_diff="Auto-detected diff (fallback orchestrator).",
                    )
                ],
                risks=[],
            )
        )
        if len(out) >= max_sections:
            break
    return out


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-zа-яё0-9\s]", " ", (text or "").lower(), flags=re.I)).strip()


