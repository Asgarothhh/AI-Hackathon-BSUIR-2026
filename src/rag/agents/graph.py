import logging
from typing import AsyncIterator, Dict, Any

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

from src.rag.agents import states
from src.rag.agents.llm_call import orchestrator, worker, assign_analysts, syntheziser

load_dotenv()
logger = logging.getLogger(__name__)

builder = StateGraph(states.State)
builder.add_node("orchestrator", orchestrator, retry_policy=RetryPolicy())
builder.add_node("worker", worker)
builder.add_node("synthesizer", syntheziser)
builder.add_edge(START, "orchestrator")
builder.add_conditional_edges("orchestrator", assign_analysts, ["worker"])
builder.add_edge("worker", "synthesizer")
builder.add_edge("synthesizer", END)
analyzer_model = builder.compile()


async def analyze_documents_stream(old_doc_text: str, new_doc_text: str) -> AsyncIterator[Dict[str, Any]]:
    initial_input = {"old_doc_text": old_doc_text, "new_doc_text": new_doc_text}
    async for chunk in analyzer_model.astream(initial_input, stream_mode="updates"):
        yield chunk


async def analyze_documents(old_doc_text: str, new_doc_text: str) -> str:
    logger.info("🚀 Запуск юридического анализа...")
    logger.info("💡 Совет: Если долго нет ответа, проверь VPN или API Key.")
    final_report = ""

    async for chunk in analyze_documents_stream(old_doc_text, new_doc_text):
        for node_name, output in chunk.items():
            logger.debug("[DEBUG] Завершен узел: %s", node_name)
            if node_name == "orchestrator":
                sections = output.get("sections_to_analyze", [])
                logger.info("✅ Оркестратор разбил документ на %s частей.", len(sections))
            elif node_name == "worker":
                analysis_items = output.get("completed_analysis") or []
                if not analysis_items:
                    continue
                analysis = analysis_items[-1]
                risks = getattr(analysis, "risks", []) or []
                risk_level = getattr(risks[0], "risk_level", "") if risks else ""
                risk_color = {"red": "🔴", "yellow": "🟡", "green": "🟢"}.get(risk_level, "⚪")
                logger.info("%s Проверен пункт %s", risk_color, getattr(analysis, "section_id", "n/a"))
            elif node_name == "synthesizer":
                final_report = str((output.get("final_report_metadata") or {}).get("text") or "").strip()
                logger.info("🏁 АНАЛИЗ ЗАВЕРШЕН. ФОРМИРУЮ ОТЧЕТ...")

    return final_report
