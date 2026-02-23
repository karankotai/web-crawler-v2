from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from rag_app.config import settings
from rag_app.models.schemas import (
    AskRequest,
    AskResponse,
    EvalQuestion,
    EvalRequest,
    EvalResponse,
    IndexRequest,
    IndexResponse,
)
from rag_app.services.eval_service import EvalService
from rag_app.services.rag_pipeline import RAGPipeline

pipeline: RAGPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    pipeline = RAGPipeline()
    print("RAG pipeline initialized")
    yield
    print("Shutting down")


app = FastAPI(
    title="Government Circulars RAG API",
    description="Ask questions about RBI, SEBI, IRDAI, and MCA circulars",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/index", response_model=IndexResponse)
async def index_documents(request: IndexRequest = IndexRequest()):
    """Index all government circulars from the output directory."""
    return pipeline.index(force_reindex=request.force_reindex)


@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """Ask a question about government circulars."""
    # Check if index exists
    info = pipeline.vector_store.collection_info()
    if not info.get("points_count", 0):
        raise HTTPException(
            status_code=400,
            detail="No documents indexed yet. Call POST /index first.",
        )
    return pipeline.ask(request)


@app.post("/evaluate", response_model=EvalResponse)
async def evaluate_question(request: EvalRequest):
    """Evaluate RAG vs vanilla LLM on a single question."""
    info = pipeline.vector_store.collection_info()
    if not info.get("points_count", 0):
        raise HTTPException(
            status_code=400,
            detail="No documents indexed yet. Call POST /index first.",
        )
    eval_service = EvalService(pipeline)
    q = EvalQuestion(
        question=request.question,
        ground_truth=request.ground_truth,
        source_filter=request.source_filter,
    )
    result = eval_service.evaluate_question(q)
    return EvalResponse(result=result)


@app.get("/health")
async def health():
    """Health check with collection info."""
    info = pipeline.vector_store.collection_info()
    return {
        "status": "healthy",
        "collection": info if info else "not indexed",
    }
