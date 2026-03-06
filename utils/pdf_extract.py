"""Shared PDF text extraction with table-aware logic."""

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
    """Extract text from PDF bytes with table-aware extraction, OCR fallback."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = _extract_page_text(page)
            if page_text:
                text_parts.append(page_text)
    result = "\n\n".join(text_parts)

    # OCR fallback for scanned/image PDFs
    if len(result.strip()) < 50:
        try:
            result = _ocr_pdf(pdf_bytes)
        except Exception:
            pass  # Return whatever pdfplumber got (may be empty)

    return result
