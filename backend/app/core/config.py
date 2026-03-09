import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw)


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY", "")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY", "")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")
    S3_FORCE_PATH_STYLE: bool = _env_bool("S3_FORCE_PATH_STYLE", False)
    S3_PRESIGNED_EXPIRES_SECONDS: int = int(os.getenv("S3_PRESIGNED_EXPIRES_SECONDS", "300"))
    S3_MAX_FILE_SIZE_MB: int = int(os.getenv("S3_MAX_FILE_SIZE_MB", "50"))
    VECTOR_DB_ENABLED: bool = _env_bool("VECTOR_DB_ENABLED", False)
    VECTOR_DB_PATH: str = os.getenv("VECTOR_DB_PATH", "./vector_db")
    VECTOR_COLLECTION: str = os.getenv("VECTOR_COLLECTION", "knowledge_chunks")
    EMBED_MODEL: str = os.getenv(
        "EMBED_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    VECTOR_CHUNK_SIZE: int = int(os.getenv("VECTOR_CHUNK_SIZE", "800"))
    VECTOR_CHUNK_OVERLAP: int = int(os.getenv("VECTOR_CHUNK_OVERLAP", "120"))
    VECTOR_TOP_K: int = int(os.getenv("VECTOR_TOP_K", "4"))
    VECTOR_MIN_SCORE: float = _env_float("VECTOR_MIN_SCORE", 0.25)
    CHAT_USE_LLM: bool = _env_bool("CHAT_USE_LLM", False)
    LLM_API_URL: str = os.getenv("LLM_API_URL", "")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")
    LLM_TEMPERATURE: float = _env_float("LLM_TEMPERATURE", 0.1)


settings = Settings()
