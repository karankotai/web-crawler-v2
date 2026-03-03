import time

from openai import OpenAI

from rag_app.config import settings


class EmbeddingService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.EMBEDDING_MODEL

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts with batching and retry."""
        all_embeddings: list[list[float]] = []
        batch_size = 100
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(texts))
            batch_texts = texts[start:end]

            print(
                f"Embedding batch {batch_idx + 1}/{total_batches} "
                f"({end}/{len(texts)} texts)"
            )

            embeddings = self._call_with_retry(batch_texts)
            all_embeddings.extend(embeddings)

        return all_embeddings

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
