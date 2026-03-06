from pathlib import Path

from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # API
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Models
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    GENERATION_MODEL: str = "gpt-4o-mini"  # Used for vanilla GPT baseline
    EVAL_JUDGE_MODEL: str = "gpt-4o"
    GEMINI_MODEL: str = "gemini-2.5-pro"  # Used for vanilla Gemini baseline
    LLM_PROVIDER: str = "gemini"  # "gemini" or "openai"
    OPENAI_GENERATION_MODEL: str = "gpt-4o-mini"

    # Qdrant
    QDRANT_URL: str = ""  # When set (e.g. http://qdrant:6333), use remote; when empty, use local path
    QDRANT_API_KEY: str = ""  # Required for Qdrant Cloud
    QDRANT_PATH: str = "rag_app/qdrant_data"
    COLLECTION_NAME: str = "gov_circulars"

    # PostgreSQL
    DATABASE_URL: str = ""  # When set, load records from PostgreSQL

    # MongoDB
    MONGODB_URI: str = ""  # When set, load records from MongoDB; when empty, use JSON files
    MONGODB_DB_NAME: str = "gov_circulars"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    # Chunking
    CHUNK_TARGET_TOKENS: int = 500
    CHUNK_MIN_TOKENS: int = 400
    CHUNK_MAX_TOKENS: int = 700
    CHUNK_OVERLAP_TOKENS: int = 50

    # Retrieval
    TOP_K: int = 12
    SCORE_THRESHOLD: float = 0.35
    MULTI_QUERY_ENABLED: bool = True

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
