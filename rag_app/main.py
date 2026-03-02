import json
import queue
import threading
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from rag_app.config import settings
from rag_app.models.schemas import (
    AskRequest,
    AskResponse,
    CrawlRequest,
    CrawlResponse,
    EvalQuestion,
    EvalRequest,
    EvalResponse,
    IndexRequest,
    IndexResponse,
)
from rag_app.services.eval_service import EvalService
from rag_app.services.rag_pipeline import RAGPipeline

pipeline: RAGPipeline | None = None
crawl_jobs: dict[str, dict] = {}


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


@app.post("/ask/stream")
async def ask_stream(request: AskRequest):
    """Stream an answer about government circulars via Server-Sent Events."""
    info = pipeline.vector_store.collection_info()
    if not info.get("points_count", 0):
        raise HTTPException(
            status_code=400,
            detail="No documents indexed yet. Call POST /index first.",
        )

    return StreamingResponse(
        pipeline.ask_stream(request.question, request.top_k, request.source_filter),
        media_type="text/event-stream",
    )


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
    result = eval_service.evaluate_question(q, baselines=request.baselines)
    return EvalResponse(result=result)


@app.get("/health")
async def health():
    """Health check with collection info."""
    info = pipeline.vector_store.collection_info()
    return {
        "status": "healthy",
        "collection": info if info else "not indexed",
    }


# ── Crawl endpoints ──────────────────────────────────────────

CRAWLER_MAP: dict[str, type] | None = None


def _get_crawler_map():
    global CRAWLER_MAP
    if CRAWLER_MAP is None:
        import sys, os

        # Add project root so `import config` / `import crawlers.*` works
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from crawlers.rbi import RBICrawler
        from crawlers.sebi import SEBICrawler
        from crawlers.mca import MCACrawler
        from crawlers.irdai import IRDAICrawler
        from crawlers.egazette import EGazetteCrawler

        CRAWLER_MAP = {
            "rbi": RBICrawler,
            "sebi": SEBICrawler,
            "mca": MCACrawler,
            "irdai": IRDAICrawler,
            "egazette": EGazetteCrawler,
        }
    return CRAWLER_MAP


def _run_crawl(task_id: str, request: CrawlRequest):
    """Run crawl in a background thread."""
    import config as crawler_config

    crawler_config.MAX_PAGES = request.max_pages
    crawler_config.DEEP_CRAWL = request.deep_crawl
    crawler_config.OUTPUT_FORMAT = request.output_format
    crawler_config.RECORD_OFFSET = request.offset

    crawlers = _get_crawler_map()
    sources = list(crawlers.keys()) if request.source == "all" else [request.source]
    total = 0

    job = crawl_jobs[task_id]
    try:
        for source_name in sources:
            crawler = crawlers[source_name]()
            results = crawler.run()
            count = len(results) if results else 0
            total += count
            job["record_count"] = total
            job["queue"].put({
                "type": "source_complete",
                "data": {"source": source_name, "record_count": count, "total_records": total},
            })

        job.update(status="completed", record_count=total)
        job["queue"].put({"type": "complete", "data": {"record_count": total}})
    except Exception as e:
        traceback.print_exc()
        job.update(status="failed", error=str(e))
        job["queue"].put({"type": "error", "data": {"message": str(e)}})


@app.post("/crawl", response_model=CrawlResponse)
async def start_crawl(request: CrawlRequest):
    """Start a web crawl in the background."""
    crawlers = _get_crawler_map()
    valid_sources = list(crawlers.keys()) + ["all"]
    if request.source not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source '{request.source}'. Choose from: {valid_sources}",
        )

    task_id = uuid.uuid4().hex[:12]
    crawl_jobs[task_id] = {
        "status": "running",
        "source": request.source,
        "record_count": 0,
        "error": None,
        "queue": queue.Queue(),
    }

    thread = threading.Thread(target=_run_crawl, args=(task_id, request), daemon=True)
    thread.start()

    return CrawlResponse(
        status="started",
        task_id=task_id,
        source=request.source,
        message=f"Crawl started for {request.source} (max {request.max_pages} pages)",
    )


@app.get("/crawl/stream/{task_id}")
async def crawl_stream(task_id: str):
    """Stream crawl progress via Server-Sent Events."""
    job = crawl_jobs.get(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")

    def generate():
        q = job["queue"]
        while True:
            try:
                event = q.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] in ("complete", "error"):
                    return
            except queue.Empty:
                yield ": keepalive\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/crawl/{task_id}")
async def crawl_status(task_id: str):
    """Check the status of a crawl job."""
    job = crawl_jobs.get(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, **{k: v for k, v in job.items() if k != "queue"}}
