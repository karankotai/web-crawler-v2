"""Configuration for the circular crawler."""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")

OUTPUT_DIR = "output"
OUTPUT_FORMAT = "both"  # "json", "csv", or "both"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_TIMEOUT = 60
PDF_TIMEOUT = 120  # longer timeout for PDF downloads
DELAY_BETWEEN_REQUESTS = 2  # seconds, be polite to servers
DEEP_CRAWL = False  # follow links and extract full notification content
MAX_PAGES = 500  # max pages to crawl per listing (safety limit)
RECORD_OFFSET = 0  # skip the first N records from crawl results
