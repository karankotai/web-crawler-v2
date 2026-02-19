from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API
    OPENAI_API_KEY: str = ""

    # Models
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    GENERATION_MODEL: str = "gpt-4o-mini"

    # Qdrant
    QDRANT_URL: str = ""  # When set (e.g. http://qdrant:6333), use remote; when empty, use local path
    QDRANT_PATH: str = "rag_app/qdrant_data"
    COLLECTION_NAME: str = "gov_circulars"

    # MongoDB
    MONGODB_URI: str = ""  # When set, load records from MongoDB; when empty, use JSON files
    MONGODB_DB_NAME: str = "gov_circulars"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    # Embedding cache
    EMBEDDING_CACHE_PATH: str = "rag_app/embedding_cache.pkl"

    # Chunking
    CHUNK_TARGET_TOKENS: int = 500
    CHUNK_MIN_TOKENS: int = 400
    CHUNK_MAX_TOKENS: int = 700
    CHUNK_OVERLAP_TOKENS: int = 50

    # Retrieval
    TOP_K: int = 8
    SCORE_THRESHOLD: float = 0.45

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
