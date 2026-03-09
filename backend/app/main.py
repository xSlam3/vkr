from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.models import chat as _chat_models  # noqa: F401
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.api import chat, knowledge, media, onboarding, users
from app.core.config import settings
from app.repositories.knowledge_repo import KnowledgeRepository
from app.services.vector_service import VectorService
from app.web import router as web_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Jewelry Onboarding API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(onboarding.router)
app.include_router(knowledge.router)
app.include_router(media.router)
app.include_router(chat.router)
app.include_router(web_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    wants_html = "text/html" in request.headers.get("accept", "").lower()
    is_get = request.method.upper() == "GET"
    is_api_request = request.url.path.startswith(("/chat", "/users", "/knowledge", "/onboarding", "/media"))

    if exc.status_code == 401 and wants_html and is_get and not is_api_request:
        return RedirectResponse("/login", status_code=303)

    raise exc


@app.on_event("startup")
def sync_vector_index() -> None:
    if not settings.VECTOR_DB_ENABLED:
        return

    db = SessionLocal()
    try:
        for article in KnowledgeRepository.list_articles(db):
            VectorService.upsert_article(
                article_id=article.id,
                title=article.title,
                text_content=article.text_content,
                category_id=article.category_id,
            )
    finally:
        db.close()
