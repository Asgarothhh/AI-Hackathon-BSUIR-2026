import os

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

from src.rag.agents import states

load_dotenv()

embeddings = OpenAIEmbeddings(model="openai/text-embedding-3-small",
                              openai_api_key=os.environ.get("OPENROUTER_API_KEY"),
                              base_url="https://openrouter.ai/api/v1")
model = ChatOpenAI(
    model="google/gemini-2.5-flash-lite",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    temperature=0,
    max_tokens=6000,
)

# planner = model.with_structured_output(states.Sections)
planner = model.with_structured_output(states.OrchestratorPlan)
analyst_llm = model.with_structured_output(states.AnalyzedSection)
