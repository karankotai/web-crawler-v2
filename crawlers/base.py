"""Base crawler class that all site-specific crawlers inherit from."""

import csv
import gc
import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import requests
from bs4 import BeautifulSoup

import config

# Known columns in the scraped_documents table.
# Any record keys not in this set go into the `extra` JSONB column.
_KNOWN_COLUMNS = {
    "source", "crawler", "title", "date", "department", "link",
    "details", "content", "circular_number", "pdf_links",
    "extraction_status", "extraction_method", "extraction_error",
    "extraction_attempts", "extraction_timestamp", "content_hash",
    "content_length", "pdf_count",
}


def _get_db_conn():
    """Return a psycopg2 connection using DATABASE_URL, or None."""
    if not config.DATABASE_URL:
        return None
    import psycopg2
    return psycopg2.connect(config.DATABASE_URL)


_table_ensured = False


def _ensure_table(conn):
    """Create the scraped_documents table and indexes if they don't exist.

    Checks whether the table already exists before running DDL to avoid
    acquiring locks that conflict with concurrent crawlers.
    """
    global _table_ensured
    if _table_ensured:
        return
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'scraped_documents')"
        )
        if cur.fetchone()[0]:
            _table_ensured = True
            return
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scraped_documents (
                id              SERIAL PRIMARY KEY,
                source          TEXT NOT NULL,
                crawler         TEXT NOT NULL,
                title           TEXT NOT NULL DEFAULT '',
                date            TEXT DEFAULT '',
                department      TEXT DEFAULT '',
                link            TEXT UNIQUE,
                details         TEXT DEFAULT '',
                content         TEXT DEFAULT '',
                circular_number TEXT DEFAULT '',
                pdf_links       JSONB DEFAULT '[]',
                extra           JSONB DEFAULT '{}',
                extraction_status    TEXT DEFAULT 'pending',
                extraction_method    TEXT DEFAULT '',
                extraction_error     TEXT DEFAULT '',
                extraction_attempts  INTEGER DEFAULT 0,
                extraction_timestamp TIMESTAMPTZ,
                content_hash         TEXT DEFAULT '',
                content_length       INTEGER DEFAULT 0,
                pdf_count            INTEGER DEFAULT 0,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_scraped_docs_crawler ON scraped_documents(crawler);
            CREATE INDEX IF NOT EXISTS idx_scraped_docs_source ON scraped_documents(source);
            CREATE INDEX IF NOT EXISTS idx_scraped_docs_extraction_status ON scraped_documents(extraction_status);
        """)
    conn.commit()
    _table_ensured = True


def _record_to_row(record, crawler_name):
    """Split a record dict into known columns + extra JSONB."""
    extra = {}
    row = {"crawler": crawler_name}
    for k, v in record.items():
        if k in _KNOWN_COLUMNS:
            if k == "pdf_links":
                row[k] = json.dumps(v if isinstance(v, list) else [])
            else:
                row[k] = v if v is not None else ""
        else:
            extra[k] = v
    # Ensure required fields have defaults
    row.setdefault("source", "")
    row.setdefault("title", "")
    row.setdefault("date", "")
    row.setdefault("department", "")
    row.setdefault("link", None)
    row.setdefault("details", "")
    row.setdefault("content", "")
    row.setdefault("circular_number", "")
    row.setdefault("pdf_links", "[]")
    row.setdefault("extraction_status", "pending")
    row.setdefault("extraction_method", "")
    row.setdefault("extraction_error", "")
    row.setdefault("extraction_attempts", 0)
    row.setdefault("content_hash", "")
    row.setdefault("content_length", 0)
    row.setdefault("pdf_count", 0)
    row["extra"] = json.dumps(extra)

    # Compute content_length and content_hash if content is present
    content = row.get("content", "")
    if content:
        row["content_length"] = len(content)
        row["content_hash"] = hashlib.sha256(content.encode()).hexdigest()

    # Compute pdf_count from pdf_links
    try:
        pdf_list = json.loads(row["pdf_links"]) if isinstance(row["pdf_links"], str) else row["pdf_links"]
        row["pdf_count"] = len(pdf_list) if isinstance(pdf_list, list) else 0
    except (json.JSONDecodeError, TypeError):
        row["pdf_count"] = 0

    return row


def _upsert_records(conn, records, crawler_name):
    """Upsert a list of record dicts into scraped_documents."""
    if not records:
        return
    with conn.cursor() as cur:
        for record in records:
            row = _record_to_row(record, crawler_name)
            if row["link"]:
                cur.execute("""
                    INSERT INTO scraped_documents
                        (source, crawler, title, date, department, link,
                         details, content, circular_number, pdf_links, extra,
                         extraction_status, extraction_method, extraction_error,
                         extraction_attempts, content_hash, content_length, pdf_count,
                         updated_at)
                    VALUES (%(source)s, %(crawler)s, %(title)s, %(date)s, %(department)s, %(link)s,
                            %(details)s, %(content)s, %(circular_number)s,
                            %(pdf_links)s::jsonb, %(extra)s::jsonb,
                            %(extraction_status)s, %(extraction_method)s, %(extraction_error)s,
                            %(extraction_attempts)s, %(content_hash)s, %(content_length)s, %(pdf_count)s,
                            NOW())
                    ON CONFLICT (link) DO UPDATE SET
                        source = EXCLUDED.source,
                        crawler = EXCLUDED.crawler,
                        title = EXCLUDED.title,
                        date = EXCLUDED.date,
                        department = EXCLUDED.department,
                        details = EXCLUDED.details,
                        content = CASE WHEN EXCLUDED.content != '' THEN EXCLUDED.content
                                       ELSE scraped_documents.content END,
                        circular_number = CASE WHEN EXCLUDED.circular_number != '' THEN EXCLUDED.circular_number
                                               ELSE scraped_documents.circular_number END,
                        pdf_links = CASE WHEN EXCLUDED.pdf_links != '[]'::jsonb THEN EXCLUDED.pdf_links
                                         ELSE scraped_documents.pdf_links END,
                        extra = EXCLUDED.extra,
                        extraction_status = CASE WHEN EXCLUDED.extraction_status != 'pending' THEN EXCLUDED.extraction_status
                                                  ELSE scraped_documents.extraction_status END,
                        extraction_method = CASE WHEN EXCLUDED.extraction_method != '' THEN EXCLUDED.extraction_method
                                                  ELSE scraped_documents.extraction_method END,
                        extraction_error = EXCLUDED.extraction_error,
                        extraction_attempts = GREATEST(EXCLUDED.extraction_attempts, scraped_documents.extraction_attempts),
                        content_hash = CASE WHEN EXCLUDED.content_hash != '' THEN EXCLUDED.content_hash
                                            ELSE scraped_documents.content_hash END,
                        content_length = GREATEST(EXCLUDED.content_length, scraped_documents.content_length),
                        pdf_count = GREATEST(EXCLUDED.pdf_count, scraped_documents.pdf_count),
                        updated_at = NOW()
                """, row)
            else:
                cur.execute("""
                    INSERT INTO scraped_documents
                        (source, crawler, title, date, department, link,
                         details, content, circular_number, pdf_links, extra,
                         extraction_status, extraction_method, extraction_error,
                         extraction_attempts, content_hash, content_length, pdf_count)
                    VALUES (%(source)s, %(crawler)s, %(title)s, %(date)s, %(department)s, %(link)s,
                            %(details)s, %(content)s, %(circular_number)s,
                            %(pdf_links)s::jsonb, %(extra)s::jsonb,
                            %(extraction_status)s, %(extraction_method)s, %(extraction_error)s,
                            %(extraction_attempts)s, %(content_hash)s, %(content_length)s, %(pdf_count)s)
                """, row)
    conn.commit()


class BaseCrawler(ABC):
    """Base class for all government circular crawlers."""

    name: str = "base"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self.results = []
        self.existing_links = set()
        self._domain_locks = {}  # per-domain rate limiting for concurrent downloads
        self._domain_locks_lock = threading.Lock()

    def load_existing(self):
        """Load previously saved results and build a set of known links."""
        # Try PostgreSQL first
        conn = _get_db_conn()
        if conn:
            try:
                _ensure_table(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT link FROM scraped_documents WHERE crawler = %s AND link IS NOT NULL",
                        (self.name,),
                    )
                    links = [row[0] for row in cur.fetchall()]
                self.existing_links = set(links)
                print(f"  Loaded {len(links)} existing links from PostgreSQL for {self.name}")
                return []  # No need to return full records; dedup uses existing_links
            except Exception as e:
                print(f"  [WARN] PostgreSQL load_existing failed: {e}")
            finally:
                conn.close()

        # Fallback to JSON
        json_path = os.path.join(config.OUTPUT_DIR, f"{self.name}.json")
        if not os.path.exists(json_path):
            return []
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            self.existing_links = {r.get("link") for r in existing if r.get("link")}
            print(f"  Loaded {len(existing)} existing records from {json_path}")
            return existing
        except (json.JSONDecodeError, KeyError):
            return []

    def fetch(self, url, method="GET", data=None, timeout=None, retries=4):
        """Fetch a URL with retry logic and polite delay.

        PDFs are streamed in chunks to avoid read timeouts on large files.
        """
        is_pdf = url.lower().endswith(".pdf")
        if timeout is None:
            timeout = config.PDF_TIMEOUT if is_pdf else config.REQUEST_TIMEOUT
        for attempt in range(1, retries + 1):
            time.sleep(config.DELAY_BETWEEN_REQUESTS)
            try:
                if method == "POST":
                    resp = self.session.post(url, data=data, timeout=timeout)
                elif is_pdf:
                    resp = self._stream_download(url, timeout)
                else:
                    resp = self.session.get(url, timeout=timeout)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                if attempt < retries:
                    wait = attempt * 5
                    print(f"  [RETRY] Attempt {attempt} failed for {url.split('/')[-1]}, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  [ERROR] Failed to fetch {url}: {e}")
                    return None

    def _stream_download(self, url, timeout):
        """Download a file in chunks using streaming to avoid read timeouts."""
        # connect timeout = 15s, per-chunk read timeout = timeout
        resp = self.session.get(url, stream=True, timeout=(15, timeout))
        resp.raise_for_status()
        chunks = []
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            chunks.append(chunk)
        resp._content = b"".join(chunks)
        return resp

    def parse_html(self, html):
        """Parse HTML content into BeautifulSoup object."""
        return BeautifulSoup(html, "lxml")

    def save_progress(self):
        """Incremental save: upsert current results to PostgreSQL (or JSON fallback).
        Called by crawlers after each page to guard against mid-crawl crashes."""
        if not self.results:
            return

        # Try PostgreSQL
        conn = _get_db_conn()
        if conn:
            try:
                _ensure_table(conn)
                _upsert_records(conn, self.results, self.name)
                print(f"  [checkpoint] Upserted {len(self.results)} records to PostgreSQL")
                return
            except Exception as e:
                print(f"  [WARN] PostgreSQL save_progress failed: {e}")
            finally:
                conn.close()

        # Fallback to JSON
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        path = os.path.join(config.OUTPUT_DIR, f"{self.name}.json")

        all_links = {r.get("link") for r in self._existing if r.get("link")}
        unique_new = [r for r in self.results if r.get("link") not in all_links]
        merged = unique_new + self._existing

        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        print(f"  [checkpoint] Saved {len(merged)} records ({len(unique_new)} new)")

    def _filter_inline(self, before_count):
        """Apply importance filter to records added since before_count.

        Called by crawlers after parsing each page/year when SELECTIVE_CRAWL is on.
        Returns the number of records filtered out.
        """
        if not config.SELECTIVE_CRAWL:
            return 0
        from crawlers.importance_filter import is_important
        new_records = self.results[before_count:]
        kept = [r for r in new_records if is_important(r)]
        filtered = len(new_records) - len(kept)
        self.results = self.results[:before_count] + kept
        return filtered

    # --- Raw Content Caching ---

    def _cache_raw_content(self, document_link, source_url, content_type, raw_bytes):
        """Store raw bytes in raw_content_cache, deduplicating by SHA256."""
        if not config.CACHE_RAW_CONTENT:
            return
        conn = _get_db_conn()
        if not conn:
            return
        try:
            content_sha256 = hashlib.sha256(raw_bytes).hexdigest()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO raw_content_cache
                        (document_link, source_url, content_type, content_sha256, raw_bytes, file_size)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (document_link, source_url) DO UPDATE SET
                        content_sha256 = EXCLUDED.content_sha256,
                        raw_bytes = EXCLUDED.raw_bytes,
                        file_size = EXCLUDED.file_size
                """, (document_link, source_url, content_type, content_sha256,
                      raw_bytes, len(raw_bytes)))
            conn.commit()
        except Exception as e:
            print(f"  [WARN] Failed to cache raw content for {source_url[:60]}: {e}")
        finally:
            conn.close()

    def _get_cached_content(self, document_link, source_url):
        """Retrieve cached raw bytes, or None if not cached."""
        conn = _get_db_conn()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT raw_bytes FROM raw_content_cache WHERE document_link = %s AND source_url = %s",
                    (document_link, source_url),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return bytes(row[0])
        except Exception as e:
            print(f"  [WARN] Cache lookup failed: {e}")
        finally:
            conn.close()
        return None

    # --- Error Tracking ---

    def _log_extraction_failure(self, document_link, source_url, error_type, error_message, attempt_number=1):
        """Log a failed extraction to the dead letter queue."""
        conn = _get_db_conn()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO failed_extractions
                        (document_link, source_url, crawler, error_type, error_message, attempt_number)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (document_link, source_url, self.name, error_type, str(error_message)[:500], attempt_number))
            conn.commit()
        except Exception as e:
            print(f"  [WARN] Failed to log extraction failure: {e}")
        finally:
            conn.close()

    def _extract_with_tracking(self, document_link, source_url, extract_fn, content_type="pdf"):
        """Wrap an extraction call with metadata tracking.

        Args:
            document_link: the record's unique link
            source_url: the URL being extracted from
            extract_fn: callable that returns (text, metadata_dict) or just text
            content_type: 'pdf' or 'html'

        Returns:
            dict with content, extraction_status, extraction_method, extraction_error
        """
        result = {
            "content": "",
            "extraction_status": "failed",
            "extraction_method": "",
            "extraction_error": "",
            "extraction_attempts": 1,
        }
        try:
            output = extract_fn()
            if isinstance(output, tuple):
                text, metadata = output
                result["extraction_method"] = metadata.get("method", content_type)
            else:
                text = output
                result["extraction_method"] = content_type

            if text and len(text.strip()) > 10:
                result["content"] = text
                result["extraction_status"] = "success"
                if len(text.strip()) < 200:
                    result["extraction_status"] = "partial"
            else:
                result["extraction_status"] = "failed"
                result["extraction_error"] = "empty_extraction"
                self._log_extraction_failure(document_link, source_url, "empty_extraction",
                                             f"Extraction returned {len(text.strip()) if text else 0} chars")
        except Exception as e:
            result["extraction_error"] = str(e)[:500]
            self._log_extraction_failure(document_link, source_url, type(e).__name__, str(e))
        return result

    # --- HTML Content Extraction ---

    def _extract_html_content(self, soup):
        """Extract main text content from an HTML page with table-to-markdown conversion.

        Used as a fallback when PDF extraction fails or returns empty.
        """
        # Find the main content container
        content_div = (
            soup.select_one("#example-min") or
            soup.select_one("#doublescroll") or
            soup.select_one("#pnlDetails") or
            soup.select_one("main") or
            soup.select_one("#content") or
            soup.select_one("article") or
            soup.select_one(".content") or
            soup.body
        )
        if not content_div:
            return ""

        parts = []

        # Convert tables to markdown
        for table in content_div.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                rows.append([c.get_text(strip=True) for c in cells])
            if rows and any(any(cell for cell in row) for row in rows):
                from utils.pdf_extract import _table_to_markdown
                md = _table_to_markdown(rows)
                if md:
                    table.replace_with(BeautifulSoup(f"\n{md}\n", "lxml"))

        text = content_div.get_text(separator="\n", strip=True)
        return text

    # --- Concurrent PDF Downloads ---

    def _get_domain_lock(self, url):
        """Get a per-domain lock for rate limiting concurrent downloads."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        with self._domain_locks_lock:
            if domain not in self._domain_locks:
                self._domain_locks[domain] = threading.Lock()
            return self._domain_locks[domain]

    def _download_and_extract_pdf(self, pdf_url, document_link):
        """Download a single PDF with rate limiting, cache it, and extract text.

        Returns (pdf_url, text, metadata) or (pdf_url, "", {}) on failure.
        """
        from utils.pdf_extract import extract_text_from_pdf_with_metadata

        # Check cache first
        cached = self._get_cached_content(document_link, pdf_url)
        if cached:
            try:
                text, metadata = extract_text_from_pdf_with_metadata(cached)
                return (pdf_url, text, metadata)
            except Exception:
                pass

        # Download with per-domain rate limiting
        lock = self._get_domain_lock(pdf_url)
        with lock:
            time.sleep(config.DELAY_PDF_DOWNLOADS)
            resp = self.fetch(pdf_url, retries=2)

        if not resp:
            return (pdf_url, "", {})

        pdf_bytes = resp.content
        if len(pdf_bytes) < 500:
            return (pdf_url, "", {})

        # Cache raw bytes
        self._cache_raw_content(document_link, pdf_url, "pdf", pdf_bytes)

        try:
            text, metadata = extract_text_from_pdf_with_metadata(pdf_bytes)
            return (pdf_url, text, metadata)
        except Exception as e:
            self._log_extraction_failure(document_link, pdf_url, "pdf_extraction", str(e))
            return (pdf_url, "", {})

    def _download_and_extract_all_pdfs(self, pdf_urls, document_link, concurrent=True):
        """Download and extract text from multiple PDFs.

        Uses concurrent downloads when config.PDF_CONCURRENT_WORKERS > 1.
        Returns concatenated text with separators.
        """
        if not pdf_urls:
            return "", "none", ""

        if len(pdf_urls) == 1 or not concurrent:
            parts = []
            method = "pdfplumber"
            for url in pdf_urls:
                _, text, meta = self._download_and_extract_pdf(url, document_link)
                if text:
                    parts.append(f"--- PDF: {url} ---\n{text}" if len(pdf_urls) > 1 else text)
                    method = meta.get("method", method)
            return "\n\n".join(parts), method, ""

        # Concurrent download for multiple PDFs
        parts = []
        method = "pdfplumber"
        workers = min(config.PDF_CONCURRENT_WORKERS, len(pdf_urls))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._download_and_extract_pdf, url, document_link): url
                for url in pdf_urls
            }
            for future in as_completed(futures):
                url = futures[future]
                try:
                    _, text, meta = future.result()
                    if text:
                        parts.append(f"--- PDF: {url} ---\n{text}" if len(pdf_urls) > 1 else text)
                        method = meta.get("method", method)
                except Exception as e:
                    self._log_extraction_failure(document_link, url, "concurrent_download", str(e))

        return "\n\n".join(parts), method, ""

    @abstractmethod
    def crawl(self):
        """Crawl the target website. Must be implemented by subclasses."""

    def crawl_details(self):
        """Follow each result's link and extract full content.

        Saves content directly to PostgreSQL after each page to guard
        against long-running deep crawls losing progress.
        """
        if not self.results:
            return
        print(f"  Deep crawling {len(self.results)} links...")
        updated = 0
        for i, record in enumerate(self.results):
            link = record.get("link", "")
            if not link:
                continue
            print(f"  [{i+1}/{len(self.results)}] {link[:80]}...")
            try:
                resp = self.fetch(link)
                if not resp:
                    continue

                # Cache detail page HTML
                self._cache_raw_content(link, link, "html", resp.content)

                soup = self.parse_html(resp.text)
                detail = self.parse_detail_page(soup, link)

                # If PDF extraction returned empty/short content, try HTML fallback
                if not detail.get("content") or len(detail.get("content", "").strip()) < 50:
                    html_content = self._extract_html_content(soup)
                    if html_content and len(html_content.strip()) > len(detail.get("content", "").strip()):
                        detail["content"] = html_content
                        detail.setdefault("extraction_method", "html_fallback")

                record.update(detail)
                # Save content to PG immediately so progress isn't lost
                if detail.get("content") and config.DATABASE_URL:
                    self._update_record_content(link, detail)
                    updated += 1
                    if updated % 50 == 0:
                        print(f"  [deep checkpoint] {updated} records with content saved to PG")
            except Exception as e:
                print(f"  [ERROR] Deep crawl failed for {link[:60]}: {e}")
                self._log_extraction_failure(link, link, "deep_crawl", str(e))
        if updated:
            print(f"  Deep crawl complete: {updated} records with content")

    def _update_record_content(self, link, detail):
        """Update a single record's content directly in PostgreSQL."""
        conn = _get_db_conn()
        if not conn:
            return
        try:
            content = detail.get("content", "")
            content_hash = hashlib.sha256(content.encode()).hexdigest() if content else ""
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE scraped_documents
                       SET content = %s,
                           pdf_links = %s::jsonb,
                           circular_number = COALESCE(NULLIF(circular_number, ''), %s),
                           extraction_status = %s,
                           extraction_method = %s,
                           extraction_error = %s,
                           extraction_attempts = GREATEST(extraction_attempts, 1),
                           extraction_timestamp = NOW(),
                           content_length = %s,
                           content_hash = %s,
                           updated_at = NOW()
                       WHERE link = %s""",
                    (
                        content,
                        json.dumps(detail.get("pdf_links", [])),
                        detail.get("circular_number", ""),
                        detail.get("extraction_status", "success" if content else "failed"),
                        detail.get("extraction_method", ""),
                        detail.get("extraction_error", ""),
                        len(content),
                        content_hash,
                        link,
                    ),
                )
            conn.commit()
        except Exception as e:
            print(f"  [WARN] Failed to save content for {link[:60]}: {e}")
        finally:
            conn.close()

    def parse_detail_page(self, soup, url):
        """Extract content from a detail page. Override for site-specific parsing."""
        # Generic: grab the largest text block on the page
        body = soup.select_one("main") or soup.select_one("#content") or soup.select_one("article") or soup.body
        content = body.get_text(separator="\n", strip=True) if body else ""
        pdf_links = [a["href"] for a in (body or soup).find_all("a", href=True) if ".pdf" in a["href"].lower()]
        return {
            "content": content,  # No truncation — removed [:5000] limit
            "pdf_links": pdf_links,
        }

    def save(self):
        """Save results to PostgreSQL (primary), with JSON/CSV as fallback."""
        if not self.results:
            print(f"  [{self.name}] No results to save.")
            return

        # Try PostgreSQL
        conn = _get_db_conn()
        if conn:
            try:
                _ensure_table(conn)
                _upsert_records(conn, self.results, self.name)
                print(f"  Saved {len(self.results)} records to PostgreSQL ({self.name})")
            except Exception as e:
                print(f"  [ERROR] PostgreSQL save failed: {e}")
            finally:
                conn.close()
            return

        # Fallback: JSON/CSV files
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        base_path = os.path.join(config.OUTPUT_DIR, self.name)

        if config.OUTPUT_FORMAT in ("json", "both"):
            path = f"{base_path}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            print(f"  Saved {len(self.results)} records to {path}")

        if config.OUTPUT_FORMAT in ("csv", "both"):
            path = f"{base_path}.csv"
            if self.results:
                # Collect all keys across all records (deep crawl adds extra fields)
                all_keys = dict.fromkeys(k for r in self.results for k in r.keys())
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=all_keys)
                    writer.writeheader()
                    for row in self.results:
                        # Convert lists to strings for CSV
                        csv_row = {}
                        for k, v in row.items():
                            csv_row[k] = ", ".join(v) if isinstance(v, list) else v
                        writer.writerow(csv_row)
                print(f"  Saved {len(self.results)} records to {path}")

        # Save to MongoDB if configured
        mongodb_uri = os.environ.get("MONGODB_URI", "")
        if mongodb_uri:
            from pymongo import MongoClient

            client = MongoClient(mongodb_uri)
            db = client["gov_circulars"]
            collection = db[self.name]
            for record in self.results:
                if record.get("link"):
                    collection.update_one({"link": record["link"]}, {"$set": record}, upsert=True)
                else:
                    collection.insert_one(record)
            client.close()
            print(f"  Saved {len(self.results)} records to MongoDB collection: {self.name}")

    def run(self):
        """Full pipeline: load existing + crawl + dedup + deep crawl + save."""
        print(f"\n{'='*60}")
        print(f"  Crawling: {self.name}")
        print(f"{'='*60}")

        self._existing = self.load_existing()

        self.crawl()

        # Dedup: filter out circulars we already have
        new_results = [r for r in self.results if r.get("link") not in self.existing_links]
        skipped = len(self.results) - len(new_results)
        if skipped:
            print(f"  Skipped {skipped} already-crawled circulars.")
        self.results = new_results

        # Apply record offset (skip first N records)
        if config.RECORD_OFFSET > 0:
            skipped_offset = min(config.RECORD_OFFSET, len(self.results))
            self.results = self.results[config.RECORD_OFFSET:]
            print(f"  Offset: skipped first {skipped_offset} records, {len(self.results)} remaining.")

        if config.SELECTIVE_CRAWL:
            from crawlers.importance_filter import filter_by_importance
            self.results, filtered_count = filter_by_importance(self.results)
            if filtered_count:
                print(f"  Selective filter: kept {len(self.results)}, filtered out {filtered_count} non-important records.")

        if config.DEEP_CRAWL:
            self.crawl_details()
            self._deep_crawl_missing_content()

        # Merge: new results first (most recent), then existing
        self.results = self.results + self._existing
        self.save()
        return self.results

    def _deep_crawl_missing_content(self):
        """Deep-crawl records already in PostgreSQL that lack content."""
        conn = _get_db_conn()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT link FROM scraped_documents WHERE crawler = %s AND (content IS NULL OR content = '') AND link IS NOT NULL",
                    (self.name,),
                )
                missing = [row[0] for row in cur.fetchall()]
        except Exception as e:
            print(f"  [WARN] Failed to query missing content: {e}")
            return
        finally:
            conn.close()

        if not missing:
            return

        print(f"  Deep crawling {len(missing)} existing records missing content...")
        updated = 0
        batch = []
        for i, link in enumerate(missing):
            print(f"  [deep {i+1}/{len(missing)}] {link[:80]}...")
            try:
                resp = self.fetch(link)
                if not resp:
                    continue

                # Cache detail page HTML
                self._cache_raw_content(link, link, "html", resp.content)

                soup = self.parse_html(resp.text)
                detail = self.parse_detail_page(soup, link)

                # HTML fallback if PDF extraction was empty
                if not detail.get("content") or len(detail.get("content", "").strip()) < 50:
                    html_content = self._extract_html_content(soup)
                    if html_content and len(html_content.strip()) > len(detail.get("content", "").strip()):
                        detail["content"] = html_content
                        detail.setdefault("extraction_method", "html_fallback")

                if detail.get("content"):
                    batch.append((link, detail))
            except Exception as e:
                print(f"  [ERROR] Deep crawl failed for {link[:60]}: {e}")
                self._log_extraction_failure(link, link, "deep_crawl_missing", str(e))

            if len(batch) >= 3:
                self._flush_deep_crawl_batch(batch)
                updated += len(batch)
                print(f"  [deep checkpoint] {updated} records with content saved to PG")
                batch = []
                gc.collect()

        if batch:
            self._flush_deep_crawl_batch(batch)
            updated += len(batch)
        if updated:
            print(f"  Deep crawl complete: {updated} records with content")

    def _flush_deep_crawl_batch(self, batch):
        """Write a batch of deep-crawled records to PostgreSQL."""
        conn = _get_db_conn()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                for link, detail in batch:
                    content = detail.get("content", "")
                    content_hash = hashlib.sha256(content.encode()).hexdigest() if content else ""
                    cur.execute(
                        """UPDATE scraped_documents
                           SET content = %s,
                               pdf_links = %s::jsonb,
                               circular_number = COALESCE(NULLIF(circular_number, ''), %s),
                               extraction_status = %s,
                               extraction_method = %s,
                               extraction_error = %s,
                               extraction_attempts = GREATEST(extraction_attempts, 1),
                               extraction_timestamp = NOW(),
                               content_length = %s,
                               content_hash = %s,
                               updated_at = NOW()
                           WHERE link = %s""",
                        (
                            content,
                            json.dumps(detail.get("pdf_links", [])),
                            detail.get("circular_number", ""),
                            detail.get("extraction_status", "success" if content else "failed"),
                            detail.get("extraction_method", ""),
                            detail.get("extraction_error", ""),
                            len(content),
                            content_hash,
                            link,
                        ),
                    )
            conn.commit()
        except Exception as e:
            print(f"  [ERROR] Failed to flush deep-crawl batch: {e}")
        finally:
            conn.close()
