import asyncio
import logging

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

from src.rag.agents import states
from src.rag.agents.llm_call import (
    orchestrator, worker,
    assign_analysts, syntheziser
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

builder = StateGraph(states.State)

builder.add_node(
    "orchestrator",
    orchestrator,
    retry_policy=RetryPolicy(),
)
builder.add_node("worker", worker)
builder.add_node("synthesizer", syntheziser)

builder.add_edge(START, "orchestrator")
builder.add_conditional_edges(
    "orchestrator",
    assign_analysts,
    ["worker"]
)

builder.add_edge("worker", "synthesizer")
builder.add_edge("synthesizer", END)

analyzer_model = builder.compile()

initial_input = {
    "old_doc_text": """
    Пункт 4.2. Заработная плата выплачивается работникам не реже двух раз в месяц 
    в дни, определенные коллективным договором (15 и 30 число).
    Пункт 5.1. Наниматель имеет право привлекать работников к дисциплинарной 
    ответственности в форме штрафа за опоздание на рабочее место более чем на 15 минут.
    """,

    "new_doc_text": """
    Пункт 4.2. Заработная плата выплачивается работникам один раз в месяц 
    20-го числа каждого месяца.
    Пункт 5.1. Наниматель обязан привлекать работников к дисциплинарной 
    ответственности в форме лишения премии и выговора за опоздание на рабочее 
    место более чем на 10 минут.
    """
}

# final_state = analyzer_model.invoke(initial_input)
# logger.info(final_state["final_report_metadata"]["text"])


async def run_analysis():
    initial_input = {
        "old_doc_text": """
        Пункт 4.2. Заработная плата выплачивается работникам не реже двух раз в месяц 
        в дни, определенные коллективным договором (15 и 30 число).
        Пункт 5.1. Наниматель имеет право привлекать работников к дисциплинарной 
        ответственности в форме штрафа за опоздание на рабочее место более чем на 15 минут.
        """,

        "new_doc_text": """
        Пункт 4.2. Заработная плата выплачивается работникам один раз в месяц 
        20-го числа каждого месяца.
        Пункт 5.1. Наниматель обязан привлекать работников к дисциплинарной 
        ответственности в форме лишения премии и выговора за опоздание на рабочее 
        место более чем на 10 минут.
        """
    }

    logger.info("🚀 Запуск юридического анализа...")
    logger.info("💡 Совет: Если долго нет ответа, проверь VPN или API Key.")

    try:
        async for chunk in analyzer_model.astream(initial_input, stream_mode="updates"):
            for node_name, output in chunk.items():
                logger.debug(f"[DEBUG] Завершен узел: {node_name}")

                if node_name == "orchestrator":
                    sections = output.get("sections_to_analyze", [])
                    logger.info(f"✅ Оркестратор разбил документ на {len(sections)} частей.")

                elif node_name == "worker":
                    analysis = output["completed_analysis"][-1]
                    risk_color = {
                        "red": "🔴",
                        "yellow": "🟡",
                        "green": "🟢"
                    }.get(analysis.risks[0].risk_level, "⚪")

                    logger.info(f"{risk_color} Проверен пункт {analysis.section_id}")

                elif node_name == "synthesizer":
                    print("🏁 АНАЛИЗ ЗАВЕРШЕН. ФОРМИРУЮ ОТЧЕТ...")
                    print("-" * 30)
                    print(output["final_report_metadata"]["text"])

    except Exception as e:
        logger.exception(f"❌ Произошла ошибка при выполнении графа: {e}")


if __name__ == "__main__":
    asyncio.run(run_analysis())
