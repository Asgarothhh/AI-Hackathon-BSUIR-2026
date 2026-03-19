import os

from dotenv import load_dotenv
from langgraph.cache.redis import RedisCache
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

from src.rag.agents import states
from src.rag.agents.llm_call import (
    orchestrator, worker,
    assign_analysts, syntheziser
)

load_dotenv()

redis_cache = RedisCache(uri=os.getenv("REDIS_URI"))

builder = StateGraph(states.State)

builder.add_node("orchestrator",
                 orchestrator,
                 retry_policy=RetryPolicy(ttl=120, ))
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

analyzer_model = builder.compile(cache=redis_cache)

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
# print(final_state["final_report_metadata"]["text"])

import asyncio


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

    print("🚀 Запуск юридического анализа...")
    print("💡 Совет: Если долго нет ответа, проверь VPN или API Key.")

    try:
        async for chunk in analyzer_model.astream(initial_input, stream_mode="updates"):
            for node_name, output in chunk.items():
                # ВАЖНО: Имя узла должно совпадать с тем, что в builder.add_node
                print(f"\n[DEBUG] Завершен узел: {node_name}")

                if node_name == "orchestrator":
                    sections = output.get("sections_to_analyze", [])
                    print(f"✅ Оркестратор разбил документ на {len(sections)} частей.")

                elif node_name == "worker":  # ИСПРАВЛЕНО с legal_worker на worker
                    # Берём последний результат из списка
                    analysis = output["completed_analysis"][-1]
                    risk_color = {"red": "🔴", "yellow": "🟡", "green": "🟢"}.get(analysis.risks[0].risk_level, "⚪")
                    print(f"{risk_color} Проверен пункт {analysis.section_id}")

                elif node_name == "synthesizer":
                    print("\n🏁 АНАЛИЗ ЗАВЕРШЕН. ФОРМИРУЮ ОТЧЕТ...")
                    print("-" * 30)
                    print(output["final_report_metadata"]["text"])

    except Exception as e:
        print(f"\n❌ Произошла ошибка при выполнении графа: {e}")


if __name__ == "__main__":
    asyncio.run(run_analysis())
