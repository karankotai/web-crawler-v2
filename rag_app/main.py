import json
import queue
import threading
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from rag_app.config import settings
from rag_app.models.schemas import (
    AnalysisChatRequest,
    AskRequest,
    AskResponse,
    CrawlRequest,
    CrawlResponse,
    EvalQuestion,
    EvalRequest,
    EvalResponse,
    IndexRequest,
    IndexResponse,
    UploadResponse,
    VALID_SOURCES,
)
from rag_app.services.eval_service import EvalService
from rag_app.prompts.ca_analysis import CA_ANALYSIS_SYSTEM_PROMPT
from rag_app.services.rag_pipeline import RAGPipeline, _sse_event

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
        pipeline.ask_stream(request.question, request.top_k, request.source_filter, request.multi_query),
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
    result = eval_service.evaluate_question(q, baselines=request.baselines, custom_answer=request.custom_answer)
    return EvalResponse(result=result)


@app.get("/health")
async def health():
    """Health check with collection info."""
    info = pipeline.vector_store.collection_info()
    return {
        "status": "healthy",
        "collection": info if info else "not indexed",
    }


# ── Upload endpoint ──────────────────────────────────────────


from utils.pdf_extract import extract_text_from_pdf as _extract_text_from_pdf


def _fetch_link_content(url: str) -> tuple[str, str]:
    """Fetch a URL and extract text content. Returns (text, title)."""
    resp = requests.get(url, timeout=60, headers={
        "User-Agent": "Mozilla/5.0 (compatible; GovCircularBot/1.0)"
    })
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        text = _extract_text_from_pdf(resp.content)
        # Use filename from URL as title fallback
        title = url.split("/")[-1].replace(".pdf", "").replace("_", " ").replace("-", " ")
        return text, title

    # HTML content
    soup = BeautifulSoup(resp.text, "lxml")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    body = soup.select_one("main") or soup.select_one("#content") or soup.select_one("article") or soup.body
    text = body.get_text(separator="\n", strip=True) if body else ""
    return text, title


def _save_records_to_pg(records: list[dict]) -> int:
    """Upsert records to PostgreSQL. Returns count saved."""
    if not settings.DATABASE_URL:
        return 0

    import sys
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from crawlers.base import _get_db_conn, _ensure_table, _upsert_records

    import config as crawler_config
    crawler_config.DATABASE_URL = settings.DATABASE_URL

    conn = _get_db_conn()
    if not conn:
        return 0
    try:
        _ensure_table(conn)
        _upsert_records(conn, records, "manual_upload")
        return len(records)
    finally:
        conn.close()


@app.post("/upload", response_model=UploadResponse)
async def upload_documents(
    source: str = Form(...),
    files: list[UploadFile] | None = Form(None),
    links: str | None = Form(None),
    title: str | None = Form(None),
    date: str | None = Form(None),
    circular_number: str | None = Form(None),
    merge: bool = Form(False, description="Merge all files/links into a single document (for original + amendments)"),
):
    """Upload PDF files or links to add to the RAG index.

    When merge=true, all uploaded PDFs and links are combined into a single
    document. Use this for a circular with its amendments — the content from
    each file is concatenated with clear section headers.
    """
    # Validate source
    if source.lower() not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source '{source}'. Choose from: {sorted(VALID_SOURCES)}",
        )

    # Parse links from JSON string
    link_list = []
    if links:
        try:
            link_list = json.loads(links)
            if not isinstance(link_list, list):
                link_list = [link_list]
        except json.JSONDecodeError:
            # Treat as newline-separated URLs
            link_list = [l.strip() for l in links.split("\n") if l.strip()]

    has_files = files and any(f.filename for f in files)
    if not has_files and not link_list:
        raise HTTPException(
            status_code=400,
            detail="At least one file or link must be provided.",
        )

    records = []
    errors = []

    # Collect content parts for merge mode
    merged_parts: list[tuple[str, str]] = []  # (label, content)
    merged_filenames: list[str] = []

    # Process PDF files
    if has_files:
        for idx, f in enumerate(files):
            if not f.filename:
                continue
            try:
                pdf_bytes = await f.read()
                content = _extract_text_from_pdf(pdf_bytes)
                file_title = f.filename.replace(".pdf", "").replace("_", " ").replace("-", " ")
                merged_filenames.append(f.filename)

                if merge:
                    label = f"Amendment {idx}" if idx > 0 else "Original"
                    merged_parts.append((f"{label} — {f.filename}", content))
                else:
                    record = {
                        "source": source.lower(),
                        "title": title or file_title,
                        "date": date or datetime.now().strftime("%Y-%m-%d"),
                        "link": f"upload://{f.filename}",
                        "content": content,
                        "circular_number": circular_number or "",
                        "pdf_links": [],
                    }
                    records.append(record)
            except Exception as e:
                errors.append(f"Failed to process {f.filename}: {e}")

    # Process links
    for idx, url in enumerate(link_list):
        try:
            content, auto_title = _fetch_link_content(url)

            if merge:
                offset = len(merged_filenames)
                label = f"Amendment {offset + idx}" if (offset + idx) > 0 else "Original"
                merged_parts.append((f"{label} — {url.split('/')[-1]}", content))
            else:
                record = {
                    "source": source.lower(),
                    "title": title or auto_title or url.split("/")[-1],
                    "date": date or datetime.now().strftime("%Y-%m-%d"),
                    "link": url,
                    "content": content,
                    "circular_number": circular_number or "",
                    "pdf_links": [url] if url.lower().endswith(".pdf") else [],
                }
                records.append(record)
        except Exception as e:
            errors.append(f"Failed to fetch {url}: {e}")

    # Build single merged record
    if merge and merged_parts:
        sections = []
        for label, content in merged_parts:
            sections.append(f"{'='*60}\n{label}\n{'='*60}\n\n{content}")
        merged_content = "\n\n".join(sections)

        first_file = merged_filenames[0] if merged_filenames else link_list[0] if link_list else "merged"
        record = {
            "source": source.lower(),
            "title": title or f"{first_file} (with {len(merged_parts) - 1} amendment(s))",
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "link": f"upload://{first_file}",
            "content": merged_content,
            "circular_number": circular_number or "",
            "pdf_links": [u for u in link_list if u.lower().endswith(".pdf")],
        }
        records.append(record)

    if not records:
        raise HTTPException(
            status_code=400,
            detail=f"No documents could be processed. Errors: {'; '.join(errors)}",
        )

    # Save to PostgreSQL
    docs_saved = _save_records_to_pg(records)

    # Index into Qdrant
    chunks_indexed = pipeline.index_records(records)

    error_suffix = f" Errors: {'; '.join(errors)}" if errors else ""
    merge_note = f" (merged {len(merged_parts)} files into 1 document)" if merge and merged_parts else ""
    return UploadResponse(
        status="success",
        documents_saved=docs_saved or len(records),
        chunks_indexed=chunks_indexed,
        message=f"Uploaded {len(records)} document(s), indexed {chunks_indexed} chunks.{merge_note}{error_suffix}",
    )


# ── Analyze endpoint ─────────────────────────────────────────


@app.post("/analyze/stream")
async def analyze_stream(
    text: str | None = Form(None),
    file: list[UploadFile] = [],
    merge: bool = Form(False),
):
    """Stream a structured CA analysis of a circular (text or PDF).

    Accepts multiple PDF files. When merge=true (or multiple files uploaded),
    all PDFs are concatenated into a single document with section headers
    so the LLM can produce a consolidated analysis.
    """
    circular_text = None

    # Filter to files that actually have content
    valid_files = [f for f in file if f.filename]

    if valid_files:
        if len(valid_files) == 1 and not merge:
            # Single file, original behaviour
            pdf_bytes = await valid_files[0].read()
            circular_text = _extract_text_from_pdf(pdf_bytes)
        else:
            # Multiple files or merge requested — concatenate with headers
            parts: list[str] = []
            for idx, f in enumerate(valid_files):
                pdf_bytes = await f.read()
                content = _extract_text_from_pdf(pdf_bytes)
                label = f"Amendment {idx}" if idx > 0 else "Original"
                parts.append(
                    f"{'=' * 60}\n{label} — {f.filename}\n{'=' * 60}\n\n{content}"
                )
            circular_text = "\n\n".join(parts)
    elif text:
        circular_text = text.strip()

    if not circular_text or len(circular_text) < 50:
        raise HTTPException(
            status_code=400,
            detail="Provide circular text (>=50 chars) or upload a PDF.",
        )

    prompt = f"<circular_text>\n{circular_text}\n</circular_text>"

    def generate():
        for chunk in pipeline.llm.generate_stream(
            prompt=prompt,
            system=CA_ANALYSIS_SYSTEM_PROMPT,
            max_tokens=8000,
            temperature=0,
        ):
            yield _sse_event("token", chunk)
        yield _sse_event("done", None)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Analyze chat endpoint ────────────────────────────────────


@app.post("/analyze/chat/stream")
async def analyze_chat_stream(request: AnalysisChatRequest):
    """Stream a follow-up answer about a previously generated analysis."""
    # Build conversation history (last 10 messages)
    history_block = ""
    if request.history:
        recent = request.history[-10:]
        turns = "\n".join(f"<{m.role}>{m.content}</{m.role}>" for m in recent)
        history_block = f"\n\n<conversation_history>\n{turns}\n</conversation_history>"

    prompt = (
        f"<analysis>\n{request.analysis_text}\n</analysis>"
        f"{history_block}"
        f"\n\n<user_question>\n{request.question}\n</user_question>"
    )

    system = (
        "You are an expert Indian Chartered Accountant (CA) assistant. "
        "You have been provided with a structured analysis of a government circular. "
        "Answer the user's follow-up questions accurately, grounding your response "
        "strictly in the provided analysis. If the analysis does not contain enough "
        "information to answer, say so clearly. Be concise and precise."
    )

    def generate():
        for chunk in pipeline.llm.generate_stream(
            prompt=prompt,
            system=system,
            max_tokens=4000,
            temperature=0,
        ):
            yield _sse_event("token", chunk)
        yield _sse_event("done", None)

    return StreamingResponse(generate(), media_type="text/event-stream")


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
