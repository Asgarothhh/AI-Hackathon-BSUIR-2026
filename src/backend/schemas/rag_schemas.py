from typing import Optional

from pydantic import BaseModel, Field


class RagRetrieveRequest(BaseModel):
    query: str = Field(..., description="User query for context retrieval")
    top_candidates: int = Field(default=12, ge=1, le=100)
    top_k: int = Field(default=5, ge=1, le=20)


class RagAskRequest(BaseModel):
    question: str = Field(..., description="Question for RAG answer generation")
    top_candidates: int = Field(default=12, ge=1, le=100)
    top_k: int = Field(default=3, ge=1, le=10)


class RagIndexBuildRequest(BaseModel):
    page_slugs: list[str] = Field(
        default_factory=list,
        description="Optional list of KB page slugs to index. Empty means all pages.",
    )
    chunk_size: int = Field(default=1200, ge=200, le=8000)
    chunk_overlap: int = Field(default=150, ge=0, le=1000)
    reset_index: bool = Field(
        default=False,
        description="Reserved for future index reset support.",
    )


class RagHit(BaseModel):
    title: str
    chapter: str
    link: str
    preview: str
    highlightText: str


class RagRetrieveResponse(BaseModel):
    query: str
    hits: list[RagHit]


class RagAskResponse(BaseModel):
    answer: str
    sources: list[RagHit]


class RagHealthResponse(BaseModel):
    ok: bool
    llm: dict
    vector_store: dict
    kb: dict

