"""Shared PDF text extraction with table-aware logic."""

import hashlib
import io
import pdfplumber


def _table_to_markdown(table: list[list]) -> str:
    """Convert a pdfplumber table (list of lists) to a markdown table string."""
    if not table or not table[0]:
        return ""
    # Clean None values and normalize newlines within cells
    cleaned = []
    for row in table:
        cleaned.append([
            str(cell).replace("\n", " ").strip() if cell else ""
            for cell in row
        ])

    # Drop columns that are entirely empty
    num_cols = len(cleaned[0])
    non_empty_cols = [
        c for c in range(num_cols)
        if any(row[c] for row in cleaned if c < len(row))
    ]
    if not non_empty_cols:
        return ""
    cleaned = [
        [row[c] if c < len(row) else "" for c in non_empty_cols]
        for row in cleaned
    ]

    # Drop rows that are entirely empty
    cleaned = [row for row in cleaned if any(cell for cell in row)]
    if not cleaned:
        return ""

    # Build markdown
    header = cleaned[0]
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in cleaned[1:]:
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[:len(header)]) + " |")
    return "\n".join(lines)


def _extract_page_text(page) -> str:
    """Extract text from a single page, handling tables separately."""
    try:
        tables = page.find_tables()
    except Exception:
        tables = []

    if not tables:
        return page.extract_text() or ""

    # Collect table bounding boxes and their markdown representations
    table_regions = []
    for table_obj in tables:
        try:
            bbox = table_obj.bbox  # (x0, top, x1, bottom)
            data = table_obj.extract()
            md = _table_to_markdown(data)
            if md:
                table_regions.append((bbox[1], bbox[3], md))  # (top, bottom, markdown)
        except Exception:
            continue

    if not table_regions:
        return page.extract_text() or ""

    # Sort regions by vertical position (top coordinate)
    table_regions.sort(key=lambda r: r[0])

    page_width = page.width
    page_height = page.height
    parts = []

    # Extract text from non-table regions by cropping
    prev_bottom = 0
    for top, bottom, md in table_regions:
        # Text region above this table
        if top > prev_bottom + 1:
            try:
                cropped = page.crop((0, prev_bottom, page_width, top))
                text = cropped.extract_text()
                if text and text.strip():
                    parts.append(text.strip())
            except Exception:
                pass
        # The table itself
        parts.append(md)
        prev_bottom = bottom

    # Text region below the last table
    if prev_bottom < page_height - 1:
        try:
            cropped = page.crop((0, prev_bottom, page_width, page_height))
            text = cropped.extract_text()
            if text and text.strip():
                parts.append(text.strip())
        except Exception:
            pass

    return "\n\n".join(parts) if parts else (page.extract_text() or "")


def _ocr_page(pdf_bytes: bytes, page_num: int) -> str:
    """OCR a single page from PDF bytes."""
    from pdf2image import convert_from_bytes
    import pytesseract

    images = convert_from_bytes(pdf_bytes, first_page=page_num + 1, last_page=page_num + 1)
    if images:
        text = pytesseract.image_to_string(images[0])
        return text.strip() if text else ""
    return ""


def _ocr_pdf(pdf_bytes: bytes) -> str:
    """OCR fallback for scanned/image-based PDFs."""
    from pdf2image import convert_from_bytes
    import pytesseract

    images = convert_from_bytes(pdf_bytes)
    parts = []
    for img in images:
        text = pytesseract.image_to_string(img)
        if text and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes with table-aware extraction, OCR fallback.

    Backward-compatible: returns just the text string.
    """
    text, _ = extract_text_from_pdf_with_metadata(pdf_bytes)
    return text


def extract_text_from_pdf_with_metadata(pdf_bytes: bytes) -> tuple[str, dict]:
    """Extract text from PDF bytes and return (text, metadata).

    Metadata includes: method, page_count, file_size, content_hash,
    has_tables, ocr_pages (list of page numbers that needed OCR).
    """
    metadata = {
        "method": "pdfplumber",
        "page_count": 0,
        "file_size": len(pdf_bytes),
        "content_hash": hashlib.sha256(pdf_bytes).hexdigest(),
        "has_tables": False,
        "ocr_pages": [],
    }

    text_parts = []
    ocr_pages = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        metadata["page_count"] = len(pdf.pages)
        for page_idx, page in enumerate(pdf.pages):
            page_text = _extract_page_text(page)

            # Per-page OCR: if a page yields very little text, OCR just that page
            if len((page_text or "").strip()) < 20:
                try:
                    ocr_text = _ocr_page(pdf_bytes, page_idx)
                    if len(ocr_text) > len(page_text or ""):
                        page_text = ocr_text
                        ocr_pages.append(page_idx)
                except Exception:
                    pass

            if page_text:
                text_parts.append(page_text)
                if "|" in page_text and "---" in page_text:
                    metadata["has_tables"] = True

    result = "\n\n".join(text_parts)

    # Full-doc OCR fallback if still very little text
    if len(result.strip()) < 50:
        try:
            ocr_result = _ocr_pdf(pdf_bytes)
            if len(ocr_result) > len(result):
                result = ocr_result
                ocr_pages = list(range(metadata["page_count"]))
        except Exception:
            pass

    metadata["ocr_pages"] = ocr_pages
    if ocr_pages:
        if len(ocr_pages) == metadata["page_count"]:
            metadata["method"] = "ocr"
        else:
            metadata["method"] = "mixed"

    return result, metadata


def extract_text_from_multiple_pdfs(pdf_items: list[tuple[str, bytes]]) -> str:
    """Extract text from multiple PDFs and concatenate with separators.

    Args:
        pdf_items: list of (url, pdf_bytes) tuples

    Returns:
        Concatenated text with --- PDF: {url} --- separators
    """
    parts = []
    for url, pdf_bytes in pdf_items:
        text = extract_text_from_pdf(pdf_bytes)
        if text and text.strip():
            parts.append(f"--- PDF: {url} ---\n{text}")
    return "\n\n".join(parts)
