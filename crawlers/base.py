"""Base crawler class that all site-specific crawlers inherit from."""

import csv
import json
import os
import time
from abc import ABC, abstractmethod

import requests
from bs4 import BeautifulSoup

import config


class BaseCrawler(ABC):
    """Base class for all government circular crawlers."""

    name: str = "base"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self.results = []
        self.existing_links = set()

    def load_existing(self):
        """Load previously saved results and build a set of known links."""
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

    def fetch(self, url, method="GET", data=None, timeout=None, retries=2):
        """Fetch a URL with retry logic and polite delay."""
        if timeout is None:
            timeout = config.PDF_TIMEOUT if url.lower().endswith(".pdf") else config.REQUEST_TIMEOUT
        for attempt in range(1, retries + 1):
            time.sleep(config.DELAY_BETWEEN_REQUESTS)
            try:
                if method == "POST":
                    resp = self.session.post(url, data=data, timeout=timeout)
                else:
                    resp = self.session.get(url, timeout=timeout)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                if attempt < retries:
                    wait = attempt * 3
                    print(f"  [RETRY] Attempt {attempt} failed for {url.split('/')[-1]}, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  [ERROR] Failed to fetch {url}: {e}")
                    return None

    def parse_html(self, html):
        """Parse HTML content into BeautifulSoup object."""
        return BeautifulSoup(html, "lxml")

    @abstractmethod
    def crawl(self):
        """Crawl the target website. Must be implemented by subclasses."""

    def crawl_details(self):
        """Follow each result's link and extract full content. Override in subclasses."""
        if not self.results:
            return
        print(f"  Deep crawling {len(self.results)} links...")
        for i, record in enumerate(self.results):
            link = record.get("link", "")
            if not link:
                continue
            print(f"  [{i+1}/{len(self.results)}] {link[:80]}...")
            resp = self.fetch(link)
            if not resp:
                continue
            soup = self.parse_html(resp.text)
            detail = self.parse_detail_page(soup, link)
            record.update(detail)

    def parse_detail_page(self, soup, url):
        """Extract content from a detail page. Override for site-specific parsing."""
        # Generic: grab the largest text block on the page
        body = soup.select_one("main") or soup.select_one("#content") or soup.select_one("article") or soup.body
        content = body.get_text(separator="\n", strip=True) if body else ""
        pdf_links = [a["href"] for a in (body or soup).find_all("a", href=True) if ".pdf" in a["href"].lower()]
        return {
            "content": content[:5000],
            "pdf_links": pdf_links,
        }

    def save(self):
        """Save results to JSON and/or CSV based on config."""
        if not self.results:
            print(f"  [{self.name}] No results to save.")
            return

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

    def run(self):
        """Full pipeline: load existing + crawl + dedup + deep crawl + save."""
        print(f"\n{'='*60}")
        print(f"  Crawling: {self.name}")
        print(f"{'='*60}")

        existing = self.load_existing()

        self.crawl()

        # Dedup: filter out circulars we already have
        new_results = [r for r in self.results if r.get("link") not in self.existing_links]
        skipped = len(self.results) - len(new_results)
        if skipped:
            print(f"  Skipped {skipped} already-crawled circulars.")
        self.results = new_results

        if config.DEEP_CRAWL:
            self.crawl_details()

        # Merge: new results first (most recent), then existing
        self.results = self.results + existing
        self.save()
        return self.results
