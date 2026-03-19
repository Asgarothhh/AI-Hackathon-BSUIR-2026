import os

from langchain_community.vectorstores import SupabaseVectorStore
from langchain_openai import OpenAIEmbeddings
from supabase.client import create_client
from dotenv import load_dotenv

load_dotenv()

supabase_client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
vector_store = SupabaseVectorStore(
    client=supabase_client,
    embedding=OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL")),
    table_name="documents",
    query_name="match_documents",
)
