from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories.knowledge_repo import KnowledgeRepository
from app.services.vector_service import VectorService


def main() -> None:
    VectorService.reset_cache()
    if not VectorService.is_ready():
        raise RuntimeError(
            "Vector DB is not ready. Check VECTOR_DB_ENABLED and installed packages from requirements.txt."
        )

    if not VectorService.recreate_collection():
        raise RuntimeError("Vector DB could not be reinitialized after collection reset.")

    db = SessionLocal()
    try:
        articles = KnowledgeRepository.list_articles(db)
        indexed_count = VectorService.sync_articles(articles)
        for article in articles:
            print(f"Indexed: {article.title}")
        print(f"Rebuilt vector collection '{settings.VECTOR_COLLECTION}' with {indexed_count} articles.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
