"""Importance-based filtering for selective recrawl.

Pre-2024: Keep master directions/circulars, amendments, and key regulatory keywords.
Post-2024: Only master circulars/directions and amendments (stricter).
"""

import re
from datetime import datetime

CUTOFF_YEAR = 2024

MASTER_PATTERNS = re.compile(
    r"\b(master\s+(direction|circular)|master\s+dir\b)", re.IGNORECASE
)

AMENDMENT_PATTERNS = re.compile(
    r"\b(amend(ment|ed|ing)?|modif(ication|ied|ying)|revis(ed|ion|ing)|updated?\s+guideline)",
    re.IGNORECASE,
)

IMPORTANCE_KEYWORDS = re.compile(
    r"\b("
    r"NPA|IRAC|KYC|AML|Basel|FEMA|ECB|NBFC|PSL|SLR|CRR|LCR"
    r"|co[\-\s]?lending|digital\s+lending|provisioning"
    r"|priority\s+sector|capital\s+adequacy|risk\s+weight"
    r"|income\s+recognition|asset\s+classification"
    r"|liquidity\s+coverage|net\s+stable\s+funding"
    r"|prompt\s+corrective\s+action|PCA"
    r"|large\s+exposure|fraud\s+reporting"
    r")\b",
    re.IGNORECASE,
)

_DATE_FORMATS = [
    "%b %d, %Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%d-%b-%Y",
    "%B %d, %Y",
    "%Y-%m-%d",
]

_INLINE_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_CIRCULAR_NUM_RE = re.compile(r"RBI/(\d{4})-(\d{4})/")
_FOUR_DIGIT_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def extract_year(record):
    """Extract the year from a record using multiple strategies.

    Returns int year or None.
    """
    # Strategy 1: Parse the date field
    date_str = (record.get("date") or "").strip()
    if date_str:
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt).year
            except ValueError:
                continue

    # Strategy 2: Inline date in details (RBI has dd.m.yyyy in pipe-delimited details)
    details = record.get("details") or ""
    m = _INLINE_DATE_RE.search(details)
    if m:
        try:
            return int(m.group(3))
        except ValueError:
            pass

    # Strategy 3: Circular number pattern RBI/YYYY-YYYY/NNN -> use second year
    title = record.get("title") or ""
    combined = title + " " + details
    m = _CIRCULAR_NUM_RE.search(combined)
    if m:
        try:
            return int(m.group(2))
        except ValueError:
            pass

    # Strategy 4: Any 4-digit year in title
    m = _FOUR_DIGIT_YEAR_RE.search(title)
    if m:
        try:
            return int(m.group(0))
        except ValueError:
            pass

    return None


def is_important(record, cutoff_year=CUTOFF_YEAR):
    """Determine if a record is important enough to keep.

    Returns True if the record should be kept.
    """
    title = record.get("title") or ""
    details = record.get("details") or ""
    text = title + " " + details

    # Master directions/circulars -> always keep
    if MASTER_PATTERNS.search(text):
        return True

    # Amendments/modifications -> always keep
    if AMENDMENT_PATTERNS.search(text):
        return True

    year = extract_year(record)

    # Post-cutoff: only master + amendments pass (checked above)
    if year is not None and year >= cutoff_year:
        return False

    # Pre-cutoff or unknown date: keep if matches regulatory keywords
    return bool(IMPORTANCE_KEYWORDS.search(text))


def filter_by_importance(records, cutoff_year=CUTOFF_YEAR):
    """Filter records by importance.

    Returns (kept_records, filtered_count).
    """
    kept = [r for r in records if is_important(r, cutoff_year)]
    return kept, len(records) - len(kept)
