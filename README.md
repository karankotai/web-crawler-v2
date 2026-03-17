# Gov Circular Crawler

Crawls circulars and notifications from Indian government regulators (RBI, SEBI, IRDAI, MCA, eGazette) and stores them in PostgreSQL. Includes a RAG pipeline for question-answering over the crawled data.

## Setup

```bash
pip install -r requirements.txt
pip install -r rag_app/requirements.txt
playwright install chromium
```

Create a `.env` file:

```
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://...
```

## Crawling

```bash
# Crawl all sources
python main.py

# Crawl a specific source
python main.py --source rbi
python main.py --source sebi
python main.py --source mca
python main.py --source irdai
python main.py --source egazette

# Limit pages crawled
python main.py --source irdai --max-pages 1

# Deep crawl (follow links and extract full content)
python main.py --source rbi --deep

# Crawl a custom government portal
python main.py --url https://example.gov.in/circulars --name "my_dept"

# Output format (only used as fallback when DATABASE_URL is not set)
python main.py --format json
python main.py --format csv
python main.py --format both
```

When `DATABASE_URL` is set, records are upserted to the `scraped_documents` PostgreSQL table. Otherwise, results are saved as JSON/CSV files in `output/`.

## RAG API

```bash
uvicorn rag_app.main:app --reload
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/index` | Index all crawled documents into the vector store |
| `POST` | `/ask` | Ask a question about government circulars |
| `POST` | `/evaluate` | Evaluate RAG vs vanilla LLM on a question |
| `GET` | `/health` | Health check with collection info |
| `POST` | `/crawl` | Start a crawl job in the background |
| `GET` | `/crawl/{task_id}` | Check crawl job status |

### Examples

```bash
# Index documents
curl -X POST http://localhost:8000/index -H "Content-Type: application/json" \ -d '{"force_reindex": true}'

# Ask a question
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "Client got a single demand order covering 2018-19 and 2020-21. Wants to settle only the older year under 128A. The order doesn't split the amount year-wise. How do I file for partial settlement?"}'

# Health check
curl http://localhost:8000/health
```

## Data Sources

| Source | Crawler | What it scrapes |
|--------|---------|-----------------|
| RBI | `rbi` | Circulars and notifications from rbi.org.in |
| SEBI | `sebi` | Circulars and master circulars from sebi.gov.in |
| MCA | `mca` | Circulars and notices from mca.gov.in |
| IRDAI | `irdai` | Circulars from irdai.gov.in |
| eGazette | `egazette` | Extra Ordinary and Weekly gazettes from egazette.gov.in |
