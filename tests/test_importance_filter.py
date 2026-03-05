"""Tests for crawlers.importance_filter module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crawlers.importance_filter import extract_year, is_important, filter_by_importance


def test_extract_year_date_formats():
    assert extract_year({"date": "Mar 04, 2026"}) == 2026
    assert extract_year({"date": "10-01-2026"}) == 2026
    assert extract_year({"date": "02.03.2026"}) == 2026
    assert extract_year({"date": "15/06/2023"}) == 2023
    assert extract_year({"date": "10-Jan-2022"}) == 2022
    assert extract_year({"date": "January 15, 2021"}) == 2021
    assert extract_year({"date": "2024-06-15"}) == 2024
    assert extract_year({"date": ""}) is None
    assert extract_year({}) is None


def test_extract_year_from_circular_number():
    assert extract_year({"title": "RBI/2025-2026/225"}) == 2026
    assert extract_year({"title": "RBI/2023-2024/100 - Some circular"}) == 2024


def test_extract_year_from_details():
    assert extract_year({"details": "SLR | 02.3.2026 | text"}) == 2026
    assert extract_year({"details": "Ref: 15.12.2019 circular"}) == 2019


def test_extract_year_from_title_fallback():
    assert extract_year({"title": "Guidelines for 2022 fiscal year"}) == 2022


def test_is_important_master_directions():
    assert is_important({"title": "Master Direction on KYC"}) is True
    assert is_important({"title": "Master Circular on NPA"}) is True
    assert is_important({"title": "master direction - updated", "date": "Mar 04, 2025"}) is True


def test_is_important_amendments():
    assert is_important({"title": "Amendment to NPA norms"}) is True
    assert is_important({"title": "Modified guidelines on lending"}) is True
    assert is_important({"title": "Revised framework for ECB", "date": "Mar 04, 2025"}) is True


def test_is_important_pre_cutoff_keyword_match():
    assert is_important({"title": "NPA classification norms", "date": "Jan 15, 2022"}) is True
    assert is_important({"title": "KYC guidelines update", "date": "Jun 10, 2020"}) is True
    assert is_important({"title": "NBFC registration rules", "date": "Mar 01, 2023"}) is True
    assert is_important({"title": "Digital lending framework", "date": "Aug 15, 2021"}) is True
    assert is_important({"title": "Priority sector lending", "date": "Jan 01, 2019"}) is True


def test_is_important_pre_cutoff_no_match():
    assert is_important({"title": "Staff memo on office timing", "date": "Jan 15, 2022"}) is False
    assert is_important({"title": "Holiday list for 2023", "date": "Dec 01, 2022"}) is False


def test_is_important_post_cutoff_non_master():
    assert is_important({"title": "Routine circular about reporting", "date": "Mar 04, 2025"}) is False
    assert is_important({"title": "NPA classification norms", "date": "Jun 15, 2024"}) is False


def test_is_important_post_cutoff_master():
    assert is_important({"title": "Master Direction on digital lending", "date": "Mar 04, 2025"}) is True


def test_is_important_unknown_date_keyword():
    assert is_important({"title": "NPA classification norms"}) is True
    assert is_important({"title": "Basel III implementation"}) is True


def test_is_important_unknown_date_no_keyword():
    assert is_important({"title": "General office circular"}) is False
    assert is_important({"title": "Routine notice to staff"}) is False


def test_is_important_details_field():
    # RBI often has keywords in details, not title
    assert is_important({"title": "Circular 123", "details": "NPA norms | 15.6.2022"}) is True
    assert is_important({"title": "Circular 123", "details": "Office memo | 15.6.2022"}) is False


def test_filter_by_importance():
    records = [
        {"title": "Master Direction on KYC", "date": "Mar 04, 2025"},
        {"title": "Staff memo on office timing", "date": "Jan 15, 2022"},
        {"title": "NPA classification norms", "date": "Jan 15, 2022"},
        {"title": "Routine circular about reporting", "date": "Mar 04, 2025"},
        {"title": "Amendment to FEMA regulations", "date": "Jun 15, 2024"},
    ]
    kept, filtered_count = filter_by_importance(records)
    assert len(kept) == 3
    assert filtered_count == 2
    kept_titles = [r["title"] for r in kept]
    assert "Master Direction on KYC" in kept_titles
    assert "NPA classification norms" in kept_titles
    assert "Amendment to FEMA regulations" in kept_titles


def test_filter_by_importance_empty():
    kept, filtered_count = filter_by_importance([])
    assert kept == []
    assert filtered_count == 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS: {test_fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test_fn.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
