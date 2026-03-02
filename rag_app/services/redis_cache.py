import json

import redis

from rag_app.config import settings


class RedisCache:
    """Redis-backed embedding cache. Stores vectors as JSON strings keyed by text hash."""

    PREFIX = "emb:"

    def __init__(self):
        self.client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        self.client.ping()
        print(f"Redis cache connected: {settings.REDIS_URL}")

    def _key(self, text_hash: str) -> str:
        return f"{self.PREFIX}{text_hash}"

    def get(self, text_hash: str) -> list[float] | None:
        raw = self.client.get(self._key(text_hash))
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, text_hash: str, embedding: list[float]) -> None:
        self.client.set(self._key(text_hash), json.dumps(embedding))

    def mget(self, text_hashes: list[str]) -> list[list[float] | None]:
        keys = [self._key(h) for h in text_hashes]
        raw_values = self.client.mget(keys)
        return [json.loads(v) if v is not None else None for v in raw_values]

    def mset(self, items: dict[str, list[float]]) -> None:
        if not items:
            return
        pipeline = self.client.pipeline()
        for text_hash, embedding in items.items():
            pipeline.set(self._key(text_hash), json.dumps(embedding))
        try:
            pipeline.execute()
        except redis.exceptions.OutOfMemoryError:
            print(f"[WARN] Redis OOM — skipped caching {len(items)} embeddings")
