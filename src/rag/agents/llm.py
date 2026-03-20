import os

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

from src.rag.agents import states

load_dotenv()

embeddings = OpenAIEmbeddings(model="openai/text-embedding-3-small",
                              openai_api_key=os.environ.get("OPENROUTER_API_KEY"),
                              base_url="https://openrouter.ai/api/v1")
planner_model = ChatOpenAI(
    model="google/gemini-2.5-flash-lite",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    temperature=0,
    # Keep planner outputs short and parseable JSON.
    max_tokens=1400,
)
analyst_model = ChatOpenAI(
    model="google/gemini-2.5-flash-lite",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    temperature=0,
    max_tokens=2800,
)

# planner = planner_model.with_structured_output(states.Sections)
planner = planner_model.with_structured_output(states.OrchestratorPlan)
analyst_llm = analyst_model.with_structured_output(states.AnalyzedSection)
