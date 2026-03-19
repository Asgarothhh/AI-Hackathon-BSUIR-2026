from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.constants import Send

from src.rag.agents import states
from src.rag.agents.llm import planner, analyst_llm


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
    prompt = "Разбей документы на логические пары пунктов. Не анализируй риски!"

    # Получаем легкий JSON (сэкономит ~70% токенов)
    response = await planner.ainvoke([
        SystemMessage(content=prompt),
        HumanMessage(content=f"Old: {state['old_doc_text']}\nNew: {state['new_doc_text']}")
    ])

    # ПРЕВРАЩАЕМ легкие модели в твои тяжелые AnalyzedSection
    full_sections = []
    for s in response.sections:
        full_sections.append(states.AnalyzedSection(
            section_id=s.section_id,
            # Кладем тексты в изменения, чтобы воркер их подхватил
            changes=[states.LegalChange(
                was_text=s.old_text,
                became_text=s.new_text,
                change_type="semantic",
                meaning_diff="Pending analysis..."
            )],
            risks=[]  # Пока пусто
        ))

    return {"sections_to_analyze": full_sections}


def worker(state: states.WorkerState):
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

    # Воркер возвращает заплоненный объект AnalyzedSection
    analysis = analyst_llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=f"Анализируемый фрагмент: {section.model_dump()}")
    ])

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
                risk_emoji = {"red": "🔴", "yellow": "🟡", "green": "🟢"}[risk.risk_level]

                line = (f"| {item.section_id} | {change.was_text} | {change.became_text} | "
                        f"{risk_emoji} {risk.risk_level} | {risk.comment} | [Link]({risk.portal_link}) |")
                report_lines.append(line)

    return {"final_report_metadata": {"text": "\n".join(report_lines)}}


def assign_analysts(state: states.State):
    """Создает воркера для каждой найденной секции"""
    return [Send("worker", {"section": s, "hierarchy_level": "All"})
            for s in state["sections_to_analyze"]
    ]


