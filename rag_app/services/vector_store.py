import hashlib

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchText,
    MatchValue,
    PointStruct,
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
            )
        else:
            self.client = QdrantClient(path=settings.QDRANT_PATH)
        self.collection_name = settings.COLLECTION_NAME

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

    def upsert_chunks(self, chunks: list[TextChunk], embeddings: list[list[float]]) -> int:
        """Upsert chunks with their embeddings into Qdrant. Returns count of points stored."""
        batch_size = 100
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
                }
                points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

            self.client.upsert(collection_name=self.collection_name, points=points)
            total_stored += len(points)

        return total_stored

    def search(
        self,
        query_vector: list[float],
        top_k: int = settings.TOP_K,
        score_threshold: float = settings.SCORE_THRESHOLD,
        source_filter: str | None = None,
        circular_number_filter: str | None = None,
    ) -> list[dict]:
        """Search for similar chunks. Returns list of dicts with text, score, metadata."""
        must_conditions = []
        if source_filter:
            must_conditions.append(
                FieldCondition(key="source", match=MatchValue(value=source_filter))
            )
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
        source_filter: str | None = None,
    ) -> list[dict]:
        """Vector search with keyword filter on text payload (OR logic for keywords)."""
        keyword_conditions = [
            FieldCondition(key="text", match=MatchText(text=kw))
            for kw in keywords
        ]
        must_conditions = []
        if source_filter:
            must_conditions.append(
                FieldCondition(key="source", match=MatchValue(value=source_filter))
            )

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
                },
            }
            for hit in results
        ]

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
