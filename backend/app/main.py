from pathlib import Path
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler as default_http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.models import chat as _chat_models  # noqa: F401
from app.models import knowledge as _knowledge_models  # noqa: F401
from app.models import onboarding as _onboarding_models  # noqa: F401
from app.models import user as _user_models  # noqa: F401
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.api import chat, knowledge, media, onboarding, users
from app.core.config import settings
from app.repositories.knowledge_repo import KnowledgeRepository
from app.services.chat_service import ChatService
from app.services.vector_service import VectorService
from app.web import router as web_router

STATIC_DIR = Path(__file__).resolve().parent / "static"
PROJECT_DIR = Path(__file__).resolve().parents[2]
LOGO_FILE = PROJECT_DIR / "logo.png"
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)


def _sync_vector_index() -> None:
    if not settings.VECTOR_DB_ENABLED or not settings.VECTOR_SYNC_ON_STARTUP:
        return

    db = SessionLocal()
    try:
        VectorService.sync_articles(KnowledgeRepository.list_articles(db))
    finally:
        db.close()


app = FastAPI(title="GemGuide.space API")

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


@app.get("/logo.png", include_in_schema=False)
def logo_file():
    return FileResponse(LOGO_FILE)

_sync_vector_index()


@app.on_event("startup")
def warm_runtime_dependencies() -> None:
    if settings.VECTOR_DB_ENABLED:
        warmed_up = VectorService.warmup()
        logger.info("Vector warmup completed=%s", warmed_up)


@app.on_event("shutdown")
def close_runtime_dependencies() -> None:
    ChatService.close_llm_client()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    wants_html = "text/html" in request.headers.get("accept", "").lower()
    is_get = request.method.upper() == "GET"
    is_api_request = request.url.path.startswith(("/chat", "/users", "/knowledge", "/onboarding", "/media"))

    if exc.status_code == 401 and wants_html and is_get and not is_api_request:
        return RedirectResponse("/login", status_code=303)

    return await default_http_exception_handler(request, exc)
