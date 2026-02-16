#!/usr/bin/env python3
"""
Government Circular/Notification Crawler

Crawls circulars and notifications from:
  - RBI (rbi.org.in)
  - SEBI (sebi.gov.in)
  - Any custom government portal URL

Usage:
    python main.py                          # Crawl all default sources
    python main.py --source rbi             # Crawl only RBI
    python main.py --source sebi            # Crawl only SEBI
    python main.py --url https://example.gov.in/circulars --name "My Dept"
    python main.py --format json            # Output only JSON (default: both)
"""

import argparse
import sys

import config
from crawlers.rbi import RBICrawler
from crawlers.sebi import SEBICrawler
from crawlers.generic import GenericGovCrawler


CRAWLERS = {
    "rbi": RBICrawler,
    "sebi": SEBICrawler,
}


def main():
    parser = argparse.ArgumentParser(description="Crawl government circulars and notifications")
    parser.add_argument(
        "--source",
        choices=list(CRAWLERS.keys()) + ["all"],
        default="all",
        help="Which source to crawl (default: all)",
    )
    parser.add_argument(
        "--url",
        help="Custom URL to crawl (use with --name)",
    )
    parser.add_argument(
        "--name",
        default="custom_gov",
        help="Name for custom URL source (default: custom_gov)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv", "both"],
        default="both",
        help="Output format (default: both)",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Follow each link and extract full notification content",
    )
    args = parser.parse_args()

    config.OUTPUT_FORMAT = args.format
    config.DEEP_CRAWL = args.deep

    total = 0

    # Custom URL mode
    if args.url:
        crawler = GenericGovCrawler(url=args.url, site_name=args.name)
        results = crawler.run()
        total += len(results)
    else:
        # Run built-in crawlers
        sources = list(CRAWLERS.keys()) if args.source == "all" else [args.source]
        for source in sources:
            crawler = CRAWLERS[source]()
            results = crawler.run()
            total += len(results)

    print(f"\n{'='*60}")
    print(f"  Done! Total records collected: {total}")
    print(f"  Output directory: {config.OUTPUT_DIR}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
