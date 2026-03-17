"""Fast reindex script that skips LLM classification.

Rule-based classification already handles most chunk types.
LLM classification of 338K chunks takes hours — skip it for now.
"""
import time
import sys
sys.path.insert(0, ".")

from rag_app.config import settings
from rag_app.services.rag_pipeline import (
    RAGPipeline,
    build_document_text,
    _normalize_date,
    _extract_circular_number,
    load_all_records_from_pg,
)
from rag_app.services.chunker import chunk_document
from rag_app.models.schemas import ChunkMetadata, IndexResponse

def main():
    start = time.time()
    pipeline = RAGPipeline()

    # Load records
    print("Loading records from PostgreSQL...")
    records = load_all_records_from_pg(settings.DATABASE_URL)
    print(f"Loaded {len(records)} records")

    records_with_content = sum(1 for r in records if r.get("content"))
    sources = sorted({r.get("source", "Unknown") for r in records})

    # Incremental mode: filter to only new records
    info = pipeline.vector_store.collection_info()
    indexed_links = pipeline.vector_store.get_indexed_links()
    new_records = [r for r in records if r.get("link", "") not in indexed_links]
    skipped = len(records) - len(new_records)
    print(f"Incremental: {skipped} already indexed, {len(new_records)} new")

    if not new_records:
        print("Nothing to index!")
        return

    # Chunk
    print("Chunking...")
    all_chunks = []
    for i, record in enumerate(new_records):
        doc_text = build_document_text(record)
        pdf_links = record.get("pdf_links", []) or []
        if record.get("pdf_link") and record["pdf_link"] not in pdf_links:
            pdf_links.append(record["pdf_link"])

        metadata = ChunkMetadata(
            source=record.get("source", "Unknown"),
            title=record.get("title", "Untitled"),
            date=_normalize_date(record.get("date", "")),
            link=record.get("link", ""),
            circular_number=_extract_circular_number(record),
            file_name=record.get("_file_name", ""),
            pdf_links=pdf_links,
        )
        chunks = chunk_document(doc_text, metadata)
        all_chunks.extend(chunks)
        if (i + 1) % 500 == 0:
            print(f"  Chunked {i+1}/{len(new_records)} records ({len(all_chunks)} chunks)")

    print(f"Created {len(all_chunks)} chunks from {len(new_records)} records")
    print("Skipping LLM classification (using rule-based types only)")

    # Embed and store
    pipeline.vector_store.ensure_collection(recreate=False)
    total_stored = 0
    batch_size = 500
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        texts = [c.text for c in batch]
        embeddings = pipeline.embedding_service.embed_texts(texts)
        total_stored += pipeline.vector_store.upsert_chunks(batch, embeddings)
        elapsed = round(time.time() - start, 1)
        print(f"  Indexed {total_stored}/{len(all_chunks)} vectors ({elapsed}s)")

    duration = round(time.time() - start, 2)
    print(f"\nDone! Indexed {total_stored} vectors in {duration}s")
    print(f"Total records: {len(records)}, with content: {records_with_content}")
    print(f"Sources: {sources}")

if __name__ == "__main__":
    main()
