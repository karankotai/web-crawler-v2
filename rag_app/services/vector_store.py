import hashlib

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    KeywordIndexParams,
    MatchAny,
    MatchText,
    MatchValue,
    PointStruct,
    TextIndexParams,
    TokenizerType,
    VectorParams,
)

from rag_app.config import settings
from rag_app.models.schemas import TextChunk


class VectorStore:
    def __init__(self):
        if settings.QDRANT_URL:
            self.client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY or None,
                timeout=60,
            )
        else:
            self.client = QdrantClient(path=settings.QDRANT_PATH)
        self.collection_name = settings.COLLECTION_NAME
        self._ensure_text_index()
        self._ensure_chunk_type_index()
        self._ensure_topic_index()
        self._ensure_source_index()

    def ensure_collection(self, recreate: bool = False):
        """Create collection, optionally recreating it."""
        if recreate:
            try:
                self.client.delete_collection(self.collection_name)
                print(f"Deleted existing collection: {self.collection_name}")
            except Exception:
                pass

        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSION, distance=Distance.COSINE),
            )
            print(f"Created collection: {self.collection_name}")
        else:
            print(f"Collection already exists: {self.collection_name}")

        self._ensure_text_index()
        self._ensure_chunk_type_index()
        self._ensure_topic_index()
        self._ensure_source_index()

    def _ensure_text_index(self):
        """Create a full-text index on the 'text' payload field if missing."""
        try:
            info = self.client.get_collection(self.collection_name)
            existing = info.payload_schema or {}
            if "text" in existing:
                return
        except Exception:
            pass

        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="text",
                field_schema=TextIndexParams(
                    type="text",
                    tokenizer=TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=20,
                    lowercase=True,
                ),
            )
            print("Created full-text index on 'text' field")
        except Exception as e:
            print(f"Text index creation skipped: {e}")

    def _ensure_chunk_type_index(self):
        """Create a keyword index on the 'chunk_type' payload field if missing."""
        try:
            info = self.client.get_collection(self.collection_name)
            existing = info.payload_schema or {}
            if "chunk_type" in existing:
                return
        except Exception:
            return

        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="chunk_type",
                field_schema=KeywordIndexParams(type="keyword"),
            )
            print("Created keyword index on 'chunk_type' field")
        except Exception as e:
            print(f"chunk_type index creation skipped: {e}")

    def _ensure_topic_index(self):
        """Create a keyword index on the 'topic' payload field if missing."""
        try:
            info = self.client.get_collection(self.collection_name)
            existing = info.payload_schema or {}
            if "topic" in existing:
                return
        except Exception:
            return

        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="topic",
                field_schema=KeywordIndexParams(type="keyword"),
            )
            print("Created keyword index on 'topic' field")
        except Exception as e:
            print(f"topic index creation skipped: {e}")

        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="circular_number",
                field_schema=KeywordIndexParams(type="keyword"),
            )
            print("Created keyword index on 'circular_number' field")
        except Exception as e:
            print(f"circular_number index creation skipped: {e}")

    def _ensure_source_index(self):
        """Create a keyword index on the 'source' payload field if missing."""
        try:
            info = self.client.get_collection(self.collection_name)
            existing = info.payload_schema or {}
            if "source" in existing:
                return
        except Exception:
            return

        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="source",
                field_schema=KeywordIndexParams(type="keyword"),
            )
            print("Created keyword index on 'source' field")
        except Exception as e:
            print(f"source index creation skipped: {e}")

    def upsert_chunks(self, chunks: list[TextChunk], embeddings: list[list[float]]) -> int:
        """Upsert chunks with their embeddings into Qdrant. Returns count of points stored."""
        batch_size = 50
        total_stored = 0

        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i : i + batch_size]
            batch_embeddings = embeddings[i : i + batch_size]

            points = []
            for chunk, embedding in zip(batch_chunks, batch_embeddings):
                # Generate stable integer ID from chunk_id
                point_id = int(hashlib.sha256(chunk.chunk_id.encode()).hexdigest()[:15], 16)
                payload = {
                    "text": chunk.text,
                    "chunk_id": chunk.chunk_id,
                    "token_count": chunk.token_count,
                    "source": chunk.metadata.source,
                    "title": chunk.metadata.title,
                    "date": chunk.metadata.date,
                    "link": chunk.metadata.link,
                    "circular_number": chunk.metadata.circular_number,
                    "chunk_index": chunk.metadata.chunk_index,
                    "total_chunks": chunk.metadata.total_chunks,
                    "file_name": chunk.metadata.file_name,
                    "pdf_links": chunk.metadata.pdf_links,
                    "chunk_type": chunk.metadata.chunk_type,
                    "topic": chunk.metadata.topic,
                    "section_index": chunk.metadata.section_index,
                    "section_heading": chunk.metadata.section_heading,
                    "context_summary": chunk.metadata.context_summary,
                }
                points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

            self.client.upsert(collection_name=self.collection_name, points=points)
            total_stored += len(points)

        return total_stored

    @staticmethod
    def _source_filter_condition(source_filter: str | list[str] | None) -> FieldCondition | None:
        """Build a Qdrant FieldCondition for source filtering.

        Supports a single source string or a list of sources (MatchAny).
        """
        if not source_filter:
            return None
        if isinstance(source_filter, list):
            if len(source_filter) == 1:
                return FieldCondition(key="source", match=MatchValue(value=source_filter[0]))
            return FieldCondition(key="source", match=MatchAny(any=source_filter))
        return FieldCondition(key="source", match=MatchValue(value=source_filter))

    def search(
        self,
        query_vector: list[float],
        top_k: int = settings.TOP_K,
        score_threshold: float = settings.SCORE_THRESHOLD,
        source_filter: str | list[str] | None = None,
        circular_number_filter: str | None = None,
    ) -> list[dict]:
        """Search for similar chunks. Returns list of dicts with text, score, metadata."""
        must_conditions = []
        src_cond = self._source_filter_condition(source_filter)
        if src_cond:
            must_conditions.append(src_cond)
        if circular_number_filter:
            must_conditions.append(
                FieldCondition(key="circular_number", match=MatchValue(value=circular_number_filter))
            )
            score_threshold = 0.0

        query_filter = Filter(must=must_conditions) if must_conditions else None

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=query_filter,
        ).points

        return [
            {
                "text": hit.payload["text"],
                "score": hit.score,
                "metadata": {
                    "source": hit.payload.get("source", ""),
                    "title": hit.payload.get("title", ""),
                    "date": hit.payload.get("date", ""),
                    "link": hit.payload.get("link", ""),
                    "circular_number": hit.payload.get("circular_number", ""),
                    "chunk_index": hit.payload.get("chunk_index", 0),
                    "total_chunks": hit.payload.get("total_chunks", 0),
                    "pdf_links": hit.payload.get("pdf_links", []),
                    "chunk_type": hit.payload.get("chunk_type", "general"),
                    "topic": hit.payload.get("topic", ""),
                    "section_heading": hit.payload.get("section_heading", ""),
                },
            }
            for hit in results
        ]

    def keyword_search(
        self,
        query_vector: list[float],
        keywords: list[str],
        top_k: int = settings.TOP_K,
        score_threshold: float = settings.SCORE_THRESHOLD,
        source_filter: str | list[str] | None = None,
    ) -> list[dict]:
        """Vector search with keyword filter on text payload (OR logic for keywords)."""
        keyword_conditions = [
            FieldCondition(key="text", match=MatchText(text=kw))
            for kw in keywords
        ]
        must_conditions = []
        src_cond = self._source_filter_condition(source_filter)
        if src_cond:
            must_conditions.append(src_cond)

        query_filter = Filter(
            should=keyword_conditions,
            must=must_conditions if must_conditions else None,
        )

        try:
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=query_filter,
            ).points
        except Exception as e:
            print(f"Keyword search failed: {e}")
            return []

        return [
            {
                "text": hit.payload["text"],
                "score": hit.score,
                "metadata": {
                    "source": hit.payload.get("source", ""),
                    "title": hit.payload.get("title", ""),
                    "date": hit.payload.get("date", ""),
                    "link": hit.payload.get("link", ""),
                    "circular_number": hit.payload.get("circular_number", ""),
                    "chunk_index": hit.payload.get("chunk_index", 0),
                    "total_chunks": hit.payload.get("total_chunks", 0),
                    "pdf_links": hit.payload.get("pdf_links", []),
                    "chunk_type": hit.payload.get("chunk_type", "general"),
                    "topic": hit.payload.get("topic", ""),
                    "section_heading": hit.payload.get("section_heading", ""),
                },
            }
            for hit in results
        ]

    def search_with_type_boost(
        self,
        query_vector: list[float],
        preferred_types: list[str],
        top_k: int = settings.TOP_K,
        score_threshold: float = settings.SCORE_THRESHOLD,
        source_filter: str | list[str] | None = None,
        boost_amount: float = 0.1,
    ) -> list[dict]:
        """Search with over-fetch and boost preferred chunk types."""
        results = self.search(
            query_vector=query_vector,
            top_k=top_k * 2,
            score_threshold=score_threshold,
            source_filter=source_filter,
        )
        for r in results:
            if r["metadata"].get("chunk_type", "general") in preferred_types:
                r["score"] += boost_amount
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def search_circular_level(
        self,
        query_vector: list[float],
        top_k_circulars: int = 5,
        source_filter: str | list[str] | None = None,
    ) -> tuple[list[tuple[str, float]], list[dict]]:
        """Over-fetch chunks, deduplicate by circular_number, return top N circular IDs
        (with scores) plus high-scoring orphan results (chunks without circular_number).

        Many IRDAI and other source documents lack a circular_number in Qdrant.
        Dropping them silently causes entire documents to become invisible to
        the hierarchical search.  Orphans are grouped by title instead and the
        best chunks from the top-scoring orphan groups are returned alongside
        the circular numbers so the caller can merge them into the final set.

        Returns:
            (ranked_circulars, orphan_results) where ranked_circulars is a list
            of (circular_number, best_score) tuples sorted by score descending.
        """
        results = self.search(
            query_vector=query_vector,
            top_k=top_k_circulars * 10,
            score_threshold=0.0,
            source_filter=source_filter,
        )
        best_per_circular: dict[str, float] = {}
        orphans_by_title: dict[str, list[dict]] = {}

        for r in results:
            cn = r["metadata"].get("circular_number", "")
            if not cn:
                title = r["metadata"].get("title", "unknown")
                orphans_by_title.setdefault(title, []).append(r)
                continue
            if cn not in best_per_circular or r["score"] > best_per_circular[cn]:
                best_per_circular[cn] = r["score"]

        ranked = sorted(best_per_circular.items(), key=lambda x: x[1], reverse=True)
        ranked_circulars = [(cn, score) for cn, score in ranked[:top_k_circulars]]

        # Rank orphan groups by best chunk score, keep top chunks from each
        orphan_groups = sorted(
            orphans_by_title.values(),
            key=lambda chunks: max(c["score"] for c in chunks),
            reverse=True,
        )
        top_orphans: list[dict] = []
        for chunks in orphan_groups[:top_k_circulars]:
            chunks.sort(key=lambda x: x["score"], reverse=True)
            top_orphans.extend(chunks[:3])

        return ranked_circulars, top_orphans

    def search_within_circulars(
        self,
        query_vector: list[float],
        circular_numbers: list[str],
        top_k_per_circular: int = 5,
    ) -> list[dict]:
        """Search within specific circulars, returning top chunks from each."""
        all_results = []
        for cn in circular_numbers:
            results = self.search(
                query_vector=query_vector,
                top_k=top_k_per_circular,
                score_threshold=0.0,
                circular_number_filter=cn,
            )
            all_results.extend(results)
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results

    def get_indexed_links(self) -> set[str]:
        """Return the set of all `link` values already stored in Qdrant."""
        links: set[str] = set()
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=None,
                limit=1000,
                offset=offset,
                with_payload=["link"],
                with_vectors=False,
            )
            for point in points:
                link = point.payload.get("link", "")
                if link:
                    links.add(link)
            if offset is None:
                break
        return links

    def collection_info(self) -> dict:
        """Get collection info, or empty dict if collection doesn't exist."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "indexed_vectors_count": info.indexed_vectors_count,
                "points_count": info.points_count,
                "status": str(info.status),
            }
        except Exception:
            return {}
