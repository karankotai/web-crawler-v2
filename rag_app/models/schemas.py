from pydantic import BaseModel, Field
from typing import Optional


class ChunkMetadata(BaseModel):
    source: str = ""
    title: str = ""
    date: str = ""
    link: str = ""
    circular_number: str = ""
    chunk_index: int = 0
    total_chunks: int = 0
    file_name: str = ""
    pdf_links: list[str] = []


class TextChunk(BaseModel):
    chunk_id: str
    text: str
    token_count: int
    metadata: ChunkMetadata


class IndexRequest(BaseModel):
    force_reindex: bool = False


class IndexResponse(BaseModel):
    total_records: int
    records_with_content: int
    total_chunks: int
    total_vectors_stored: int
    sources_indexed: list[str]
    duration_seconds: float


class AskRequest(BaseModel):
    question: str
    top_k: int = Field(default=8, ge=1, le=20)
    source_filter: Optional[str] = None


class SourceReference(BaseModel):
    title: str
    source: str
    date: str
    link: str
    circular_number: str
    relevance_score: float
    pdf_links: list[str] = []


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    query_used: str
    chunks_retrieved: int
