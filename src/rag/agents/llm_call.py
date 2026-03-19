import logging

from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_tavily import TavilySearch
from langgraph.constants import Send

from src.rag.agents import states
from src.rag.agents.llm import planner, analyst_llm
from src.rag.vectorstore.store import vector_store

logger = logging.getLogger(__name__)

tavily_tool = TavilySearch(
    max_results=3,
    include_domains=["pravo.by", "etalonline.by", "law.by"],
    exclude_domains=["kodeksy-by.com"]
)


async def orchestrator(state: states.State):
    logger.debug("Запуск orchestrator")

    prompt = "Разбей документы на логические пары пунктов. Не анализируй риски!"

    response = await planner.ainvoke([
        SystemMessage(content=prompt),
        HumanMessage(content=f"Old: {state['old_doc_text']}\nNew: {state['new_doc_text']}")
    ])

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

    logger.info(f"Orchestrator создал {len(full_sections)} секций для анализа")
    return {"sections_to_analyze": full_sections}


async def worker(state: states.WorkerState):
    """Асинхронный воркер: ищет в Tavily, сохраняет в Supabase, анализирует риски."""
    logger.debug("Запуск worker")

    section = state["section"]
    became_text = section.changes[0].became_text if section.changes else "Общие нормы законодательства РБ"

    # Формируем запрос
    search_query = (
        f'официальный текст НПА Республики Беларусь "{became_text}" '
        f'(Эталон ONLINE OR pravo.by OR law.by)'
    )

    try:
        search_results = await tavily_tool.ainvoke({"query": search_query})
    except Exception as e:
        logger.error(f"Ошибка при поиске Tavily: {e}")
        search_results = []

    docs_to_save = []
    context_texts = []

    # Безопасная обработка результатов поиска
    if isinstance(search_results, list):
        for res in search_results:
            # Если результат - словарь (как ожидается)
            if isinstance(res, dict):
                content = res.get("content", "")
                url = res.get("url", "интернет-ресурс")
            # Если вдруг пришла просто строка
            else:
                content = str(res)
                url = "архив НЦПИ"

            if content:
                context_texts.append(f"Источник ({url}):\n{content}")
                docs_to_save.append(
                    Document(
                        page_content=content,
                        metadata={"source": url, "section_id": section.section_id}
                    )
                )
    elif isinstance(search_results, str):
        context_texts.append(search_results)
        docs_to_save.append(Document(page_content=search_results, metadata={"source": "tavily_summary"}))

    # Сохранение в Supabase
    if docs_to_save:
        try:
            await vector_store.aadd_documents(docs_to_save)
            logger.debug(f"Сохранено {len(docs_to_save)} док. в Supabase для {section.section_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения в Supabase: {e}")

    context_str = "\n\n".join(context_texts) if context_texts else "Внешние источники не найдены."

    # Анализ LLM
    prompt = f"""Проведи юридическую экспертизу пункта {section.section_id}.
    Используй предоставленный КОНТЕКСТ из законов РБ для выявления рисков.

    КОНТЕКСТ:
    {context_str}
    """

    analysis = await analyst_llm.ainvoke([
        SystemMessage(content=prompt),
        HumanMessage(content=f"Данные секции: {section.model_dump_json()}")
    ])

    return {"completed_analysis": [analysis]}


def syntheziser(state: states.State):
    logger.debug("Запуск synthesizer")

    results = state["completed_analysis"]

    report_lines = [
        "# Отчет об анализе изменений НПА\n",
        "| Пункт | Было | Стало | Риск | Рекомендация | Ссылка |",
        "|-------|------|-------|------|--------------|--------|"
    ]

    for item in results:
        for change in item.changes:
            for risk in item.risks:
                risk_emoji = {
                    "red": "🔴",
                    "yellow": "🟡",
                    "green": "🟢"
                }.get(risk.risk_level, "⚪")

                # Безопасное форматирование на случай отсутствия portal_link
                link_md = f"[Link]({risk.portal_link})" if risk.portal_link else "Нет"

                line = (
                    f"| {item.section_id} | {change.was_text} | {change.became_text} | "
                    f"{risk_emoji} {risk.risk_level} | {risk.comment} | {link_md} |"
                )
                report_lines.append(line)

    logger.info("Synthesizer сформировал финальный отчет")
    return {"final_report_metadata": {"text": "\n".join(report_lines)}}


def assign_analysts(state: states.State):
    logger.debug("Назначение воркеров для секций")

    tasks = [
        Send("worker", {"section": s, "hierarchy_level": "All"})
        for s in state["sections_to_analyze"]
    ]

    logger.info(f"Создано {len(tasks)} задач для воркеров")
    return tasks
