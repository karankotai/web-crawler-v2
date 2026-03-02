import hashlib
import pickle
import time
from pathlib import Path

from openai import OpenAI

from rag_app.config import settings

CACHE_PATH = Path(settings.EMBEDDING_CACHE_PATH)


class EmbeddingService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.EMBEDDING_MODEL
        self.redis = None
        self.cache: dict[str, list[float]] = {}

        if settings.REDIS_URL:
            try:
                from rag_app.services.redis_cache import RedisCache

                self.redis = RedisCache()
            except Exception as e:
                print(f"Redis unavailable, falling back to pickle cache: {e}")
                self._load_pickle_cache()
        else:
            self._load_pickle_cache()

    def _load_pickle_cache(self):
        if CACHE_PATH.exists():
            try:
                with open(CACHE_PATH, "rb") as f:
                    self.cache = pickle.load(f)
                print(f"Loaded {len(self.cache)} cached embeddings from pickle")
            except Exception as e:
                print(f"Cache load failed, starting fresh: {e}")
                self.cache = {}

    def _save_pickle_cache(self):
        with open(CACHE_PATH, "wb") as f:
            pickle.dump(self.cache, f)

    @staticmethod
    def _text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts with caching and batching."""
        results: list[tuple[int, list[float]]] = []
        uncached: list[tuple[int, str]] = []
        hashes = [self._text_hash(t) for t in texts]

        if self.redis:
            cached_values = self.redis.mget(hashes)
            for i, emb in enumerate(cached_values):
                if emb is not None:
                    results.append((i, emb))
                else:
                    uncached.append((i, texts[i]))
        else:
            for i, text in enumerate(texts):
                if hashes[i] in self.cache:
                    results.append((i, self.cache[hashes[i]]))
                else:
                    uncached.append((i, text))

        if uncached:
            print(f"Cache hit: {len(results)}, need to embed: {len(uncached)}")
            batch_size = 100
            total_batches = (len(uncached) + batch_size - 1) // batch_size
            new_embeddings: dict[str, list[float]] = {}

            for batch_idx in range(total_batches):
                start = batch_idx * batch_size
                end = min(start + batch_size, len(uncached))
                batch = uncached[start:end]
                batch_texts = [t for _, t in batch]

                print(
                    f"Embedding batch {batch_idx + 1}/{total_batches} "
                    f"({end}/{len(uncached)} texts)"
                )

                embeddings = self._call_with_retry(batch_texts)
                for (orig_idx, text), emb in zip(batch, embeddings):
                    h = self._text_hash(text)
                    new_embeddings[h] = emb
                    results.append((orig_idx, emb))

            # Persist new embeddings to cache
            if self.redis:
                self.redis.mset(new_embeddings)
            else:
                self.cache.update(new_embeddings)
                self._save_pickle_cache()

        results.sort(key=lambda x: x[0])
        return [emb for _, emb in results]

    def embed_single(self, text: str) -> list[float]:
        """Embed a single query text."""
        response = self.client.embeddings.create(
            input=[text],
            model=self.model,
        )
        return response.data[0].embedding

    def _call_with_retry(
        self, texts: list[str], max_retries: int = 3
    ) -> list[list[float]]:
        for attempt in range(max_retries):
            try:
                response = self.client.embeddings.create(
                    input=texts,
                    model=self.model,
                )
                return [d.embedding for d in response.data]
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** (attempt + 1)
                print(f"Embedding API error (attempt {attempt + 1}): {e}. Retrying in {wait}s...")
                time.sleep(wait)
        return []  # unreachable
