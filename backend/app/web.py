from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.repositories.user_repo import UserRepository
from app.schemas.knowledge import CategoryCreate, KnowledgeArticleCreate, KnowledgeArticleUpdate
from app.schemas.onboarding import OnboardingDayCreate, OnboardingDayUpdate
from app.schemas.user import UserCreate
from app.services.chat_service import ChatService
from app.services.chat_history_service import ChatHistoryService
from app.services.knowledge_service import KnowledgeService
from app.services.onboarding_service import OnboardingService
from app.services.s3_service import S3Service
from app.services.user_service import UserService

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%d.%m.%Y %H:%M")


async def _read_form(request: Request) -> dict[str, str]:
    raw = await request.body()
    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1].strip() for key, values in parsed.items()}


def _redirect(path: str, *, message: str | None = None, error: str | None = None) -> RedirectResponse:
    query: dict[str, str] = {}
    if message:
        query["message"] = message
    if error:
        query["error"] = error
    location = path
    if query:
        location = f"{path}?{urlencode(query)}"
    return RedirectResponse(location, status_code=status.HTTP_303_SEE_OTHER)


def _login_context(
    request: Request,
    *,
    has_users: bool,
    error: str | None = None,
    message: str | None = None,
) -> dict:
    heading = "Вход в систему" if has_users else "Первичная настройка"
    subtext = (
        "Введите логин и пароль, чтобы открыть рабочий кабинет."
        if has_users
        else "Создайте первого администратора. После этого можно будет входить в систему."
    )
    return {
        "request": request,
        "title": f"{heading} - GemGuide.space",
        "page_name": "login",
        "has_users": has_users,
        "heading": heading,
        "subtext": subtext,
        "action": "/login" if has_users else "/setup",
        "submit_label": "Вход" if has_users else "Создать администратора",
        "error": error,
        "message": message,
    }


def _serialize_users(users: list[User]) -> list[dict]:
    return [
        {
            "username": user.username,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "created_at": _format_datetime(user.created_at),
        }
        for user in users
    ]


def _serialize_onboarding_items(items: list, current_user: User) -> list[dict]:
    serialized: list[dict] = []
    for item in items:
        media_type = getattr(getattr(item, "media_type", None), "value", None) or getattr(item, "media_type", None)
        completed = bool(getattr(item, "completed", False))
        text_content = item.text_content or ""
        serialized.append(
            {
                "id": item.id,
                "day_number": item.day_number,
                "title": item.title,
                "text_content": _rewrite_rich_media_sources(text_content),
                "text_preview": _summarize_rich_text(text_content),
                "media_type": media_type or "-",
                "media_url": _resolve_media_url(getattr(item, "media_url", None) or ""),
                "completed": completed,
                "completed_at": _format_datetime(getattr(item, "completed_at", None)) if completed else None,
                "show_complete_action": current_user.role == UserRole.employee and not completed,
            }
        )
    return serialized


def _build_onboarding_progress(items: list[dict], current_user: User) -> dict | None:
    if current_user.role != UserRole.employee:
        return None

    total = len(items)
    completed = sum(1 for item in items if item["completed"])
    percent = int(round((completed / total) * 100)) if total else 0
    return {
        "total": total,
        "completed": completed,
        "remaining": max(total - completed, 0),
        "percent": percent,
    }


def _serialize_categories(categories: list, selected_category_id: str = "") -> list[dict]:
    return [
        {
            "id": category.id,
            "name": category.name,
            "selected": category.id == selected_category_id,
        }
        for category in categories
    ]


def _summarize_rich_text(value: str, max_length: int = 180) -> str:
    plain = re.sub(r"<[^>]+>", " ", value or "")
    plain = html.unescape(plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) <= max_length:
        return plain
    return plain[: max_length - 1].rstrip() + "…"


def _format_chat_message(value: str) -> str:
    escaped = html.escape((value or "").strip())
    if not escaped:
        return ""

    normalized = escaped.replace("\r\n", "\n").replace("\r", "\n")

    def replace_bold(match: re.Match[str]) -> str:
        return f"<strong>{match.group(1).strip()}</strong>"

    blocks: list[str] = []
    for raw_block in re.split(r"\n{2,}", normalized):
        block = raw_block.strip()
        if not block:
            continue
        block = re.sub(r"\*\*(.+?)\*\*", replace_bold, block)
        block = block.replace("\n", "<br>")
        blocks.append(f"<p>{block}</p>")

    return "".join(blocks)


def _resolve_media_url(value: str) -> str:
    key = S3Service.key_from_url(value)
    if key:
        return f"/media/file?key={key}"
    return value


def _optional_form_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or normalized.lower() in {"none", "null", "undefined"}:
        return None
    return normalized


def _parse_day_number(value: str | None, *, fallback: int | None = None) -> int:
    normalized = _optional_form_value(value)
    if normalized is None:
        if fallback is not None:
            return fallback
        raise ValueError("Day number is required")
    try:
        return int(normalized)
    except ValueError:
        match = re.search(r"\d+", normalized)
        if match:
            return int(match.group())
        if fallback is not None:
            return fallback
        raise ValueError(f"Invalid day number: {normalized}")


def _rewrite_rich_media_sources(value: str) -> str:
    if not value:
        return value

    def replace_attr(match: re.Match[str]) -> str:
        prefix = match.group(1)
        url = match.group(2)
        suffix = match.group(3)
        return f"{prefix}{_resolve_media_url(url)}{suffix}"

    return re.sub(r'((?:src|href)=["\'])([^"\']+)(["\'])', replace_attr, value)


def _serialize_articles(articles: list, categories: list) -> list[dict]:
    category_lookup = {category.id: category.name for category in categories}
    return [
        {
            "id": article.id,
            "title": article.title,
            "raw_text_content": article.text_content or "",
            "text_content": _rewrite_rich_media_sources(article.text_content or ""),
            "text_preview": _summarize_rich_text(article.text_content or "", 220),
            "category_name": category_lookup.get(article.category_id, "Без категории"),
            "category_id": article.category_id,
            "updated_at": _format_datetime(article.updated_at),
            "media_type": article.media_type.value if getattr(article.media_type, "value", None) else "-",
            "raw_media_url": article.media_url or "",
            "media_url": _resolve_media_url(article.media_url or ""),
        }
        for article in articles
    ]


def _serialize_chat_response(chat_response) -> dict | None:
    if not chat_response:
        return None
    return {
        "answer": chat_response.answer,
        "answer_html": _format_chat_message(chat_response.answer),
        "sources": [
            {
                "title": source.title or source.article_id,
                "score": f"{source.score:.3f}" if source.score is not None else None,
            }
            for source in chat_response.sources
        ],
    }


def _serialize_chat_sessions(sessions: list, active_session_id: str = "") -> list[dict]:
    return [
        {
            "id": session.id,
            "title": session.title,
            "updated_at": _format_datetime(session.updated_at),
            "active": session.id == active_session_id,
        }
        for session in sessions
    ]


def _serialize_chat_messages(messages: list) -> list[dict]:
    return [
        {
            "id": message.id,
            "role": message.role.value if hasattr(message.role, "value") else str(message.role),
            "content": message.content,
            "content_html": _format_chat_message(message.content),
        }
        for message in messages
    ]


def _build_bottom_nav(current_user: User, active_page: str) -> list[dict]:
    items = [
        {"key": "home", "label": "Главная", "href": "/dashboard", "icon": "⌂"},
        {"key": "onboarding", "label": "Адаптация", "href": "/onboarding", "icon": "◎"},
        {"key": "knowledge", "label": "Статьи", "href": "/knowledge", "icon": "▤"},
        {"key": "assistant", "label": "Чат", "href": "/assistant", "icon": "◌"},
    ]
    if current_user.role == UserRole.admin:
        items.append({"key": "admin", "label": "Админ", "href": "/admin", "icon": "★"})
    for item in items:
        item["active"] = item["key"] == active_page
    return items


def _base_app_context(
    request: Request,
    current_user: User,
    *,
    title: str,
    page_name: str,
    active_page: str,
    message: str | None = None,
    error: str | None = None,
) -> dict:
    return {
        "request": request,
        "title": title,
        "page_name": page_name,
        "current_user": {
            "username": current_user.username,
            "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            "is_admin": current_user.role == UserRole.admin,
        },
        "message": message,
        "error": error,
        "bottom_nav": _build_bottom_nav(current_user, active_page),
    }


def _home_context(
    request: Request,
    db: Session,
    current_user: User,
    *,
    message: str | None = None,
    error: str | None = None,
) -> dict:
    onboarding_items = _serialize_onboarding_items(
        OnboardingService.list_days(db) if current_user.role == UserRole.admin else OnboardingService.get_my_onboarding(db, current_user),
        current_user,
    )
    categories = KnowledgeService.list_categories(db)
    all_articles = KnowledgeService.list_articles(db)
    context = _base_app_context(
        request,
        current_user,
        title="Главная - GemGuide.space",
        page_name="dashboard-home",
        active_page="home",
        message=message,
        error=error,
    )
    context.update(
        {
            "stats": [
                {"label": "Дней адаптации", "value": len(onboarding_items), "href": "/onboarding"},
                {"label": "Категорий", "value": len(categories), "href": "/knowledge"},
                {"label": "Статей", "value": len(all_articles), "href": "/knowledge"},
            ],
            "recent_onboarding": onboarding_items[:3],
            "recent_articles": _serialize_articles(all_articles[:3], categories),
            "quick_links": [
                {"title": "Материалы адаптации", "text": "Открыть дни и отметить прогресс.", "href": "/onboarding"},
                {"title": "База знаний", "text": "Поиск по статьям и категориям.", "href": "/knowledge"},
                {"title": "Ассистент", "text": "Задать вопрос по статьям.", "href": "/assistant"},
            ],
        }
    )
    if current_user.role == UserRole.admin:
        context["quick_links"].append({"title": "Администрирование", "text": "Пользователи и контент.", "href": "/admin"})
    return context


def _onboarding_context(
    request: Request,
    db: Session,
    current_user: User,
    *,
    message: str | None = None,
    error: str | None = None,
) -> dict:
    items = OnboardingService.list_days(db) if current_user.role == UserRole.admin else OnboardingService.get_my_onboarding(db, current_user)
    context = _base_app_context(
        request,
        current_user,
        title="Адаптация - GemGuide.space",
        page_name="onboarding",
        active_page="onboarding",
        message=message,
        error=error,
    )
    context["onboarding_items"] = _serialize_onboarding_items(items, current_user)
    context["onboarding_progress"] = _build_onboarding_progress(context["onboarding_items"], current_user)
    used_numbers = {item.day_number for item in items}
    context["day_slots"] = [
        {
            "value": value,
            "available": value not in used_numbers,
        }
        for value in range(1, 8)
    ]
    return context


def _onboarding_day_context(
    request: Request,
    db: Session,
    current_user: User,
    day_id: str,
    *,
    message: str | None = None,
    error: str | None = None,
) -> dict:
    items = OnboardingService.list_days(db) if current_user.role == UserRole.admin else OnboardingService.get_my_onboarding(db, current_user)
    serialized_items = _serialize_onboarding_items(items, current_user)
    day = next((item for item in serialized_items if item["id"] == day_id), None)
    if not day:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="День адаптации не найден.")

    context = _base_app_context(
        request,
        current_user,
        title=f"День {day['day_number']} - GemGuide.space",
        page_name="onboarding-day",
        active_page="onboarding",
        message=message,
        error=error,
    )
    context["onboarding_day"] = day
    context["onboarding_progress"] = _build_onboarding_progress(serialized_items, current_user)
    used_numbers = {item["day_number"] for item in serialized_items if item["id"] != day_id}
    context["day_slots"] = [
        {
            "value": value,
            "available": value not in used_numbers,
        }
        for value in range(1, 8)
    ]
    return context


def _knowledge_context(
    request: Request,
    db: Session,
    current_user: User,
    *,
    article_search: str = "",
    category_id: str = "",
    message: str | None = None,
    error: str | None = None,
) -> dict:
    categories = KnowledgeService.list_categories(db)
    articles = KnowledgeService.list_articles(db, search=article_search or None, category_id=category_id or None)
    context = _base_app_context(
        request,
        current_user,
        title="База знаний - GemGuide.space",
        page_name="knowledge",
        active_page="knowledge",
        message=message,
        error=error,
    )
    context.update(
        {
            "article_search": article_search,
            "categories": _serialize_categories(categories, category_id),
            "articles": _serialize_articles(articles, categories),
        }
    )
    return context


def _knowledge_article_context(
    request: Request,
    db: Session,
    current_user: User,
    article_id: str,
    *,
    message: str | None = None,
    error: str | None = None,
) -> dict:
    categories = KnowledgeService.list_categories(db)
    article = _serialize_articles([KnowledgeService.get_article(db, article_id)], categories)[0]
    context = _base_app_context(
        request,
        current_user,
        title=f"{article['title']} - GemGuide.space",
        page_name="knowledge-article",
        active_page="knowledge",
        message=message,
        error=error,
    )
    context["categories"] = _serialize_categories(categories, article["category_id"])
    context["article"] = article
    return context


def _assistant_context(
    request: Request,
    db: Session,
    current_user: User,
    *,
    chat_id: str = "",
    chat_question: str = "",
    chat_response=None,
    message: str | None = None,
    error: str | None = None,
) -> dict:
    sessions = ChatHistoryService.list_sessions(db, current_user)
    messages = ChatHistoryService.get_messages(db, current_user, chat_id) if chat_id else []
    context = _base_app_context(
        request,
        current_user,
        title="Ассистент - GemGuide.space",
        page_name="assistant",
        active_page="assistant",
        message=message,
        error=error,
    )
    context.update(
        {
            "active_chat_id": chat_id,
            "chat_question": chat_question,
            "chat_sessions": _serialize_chat_sessions(sessions, chat_id),
            "chat_messages": _serialize_chat_messages(messages),
            "chat_response": _serialize_chat_response(chat_response),
        }
    )
    return context


def _admin_context(
    request: Request,
    db: Session,
    current_user: User,
    *,
    message: str | None = None,
    error: str | None = None,
) -> dict:
    context = _base_app_context(
        request,
        current_user,
        title="Администрирование - GemGuide.space",
        page_name="admin",
        active_page="admin",
        message=message,
        error=error,
    )
    context.update(
        {
            "users": _serialize_users(UserService.list_users(db)),
        }
    )
    return context


def _require_admin_page(current_user: User) -> None:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав.")


@router.get("/")
def root(current_user: User | None = Depends(get_current_user_optional)):
    return RedirectResponse("/dashboard" if current_user else "/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login")
def login_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
    error: str | None = None,
    message: str | None = None,
):
    if current_user:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "login.html",
        _login_context(request, has_users=UserRepository.count(db) > 0, error=error, message=message),
    )


@router.post("/setup")
async def setup_first_admin(request: Request, db: Session = Depends(get_db)):
    if UserRepository.count(db) > 0:
        return _redirect("/login", error="Первый пользователь уже создан. Используйте форму входа.")
    form = await _read_form(request)
    try:
        user = UserService.create_user(
            db,
            UserCreate(username=form.get("username", ""), password=form.get("password", ""), role="admin"),
        )
    except (HTTPException, ValidationError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else "Заполните логин и пароль."
        return templates.TemplateResponse(
            request,
            "login.html",
            _login_context(request, has_users=False, error=str(detail)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    response = _redirect("/dashboard", message=f"Администратор {user.username} создан.")
    response.set_cookie("access_token", create_access_token(subject=user.id), httponly=True, samesite="lax", path="/")
    return response


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    form = await _read_form(request)
    has_users = UserRepository.count(db) > 0
    if not form.get("username") or not form.get("password"):
        return templates.TemplateResponse(
            request,
            "login.html",
            _login_context(request, has_users=has_users, error="Заполните логин и пароль."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        user = UserService.authenticate(db, form.get("username", ""), form.get("password", ""))
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            _login_context(request, has_users=has_users, error=str(exc.detail)),
            status_code=exc.status_code,
        )
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("access_token", create_access_token(subject=user.id), httponly=True, samesite="lax", path="/")
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token", path="/")
    return response


@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    message: str | None = None,
    error: str | None = None,
):
    return templates.TemplateResponse(request, "dashboard.html", _home_context(request, db, current_user, message=message, error=error))


@router.get("/onboarding")
def onboarding_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    message: str | None = None,
    error: str | None = None,
):
    return templates.TemplateResponse(request, "onboarding.html", _onboarding_context(request, db, current_user, message=message, error=error))


@router.get("/onboarding/{day_id}")
def onboarding_day_page(
    day_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    message: str | None = None,
    error: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "onboarding_day.html",
        _onboarding_day_context(request, db, current_user, day_id, message=message, error=error),
    )


@router.get("/knowledge")
def knowledge_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    message: str | None = None,
    error: str | None = None,
    search: str = "",
    category_id: str = "",
):
    return templates.TemplateResponse(
        request,
        "knowledge.html",
        _knowledge_context(request, db, current_user, article_search=search, category_id=category_id, message=message, error=error),
    )


@router.get("/knowledge/{article_id}")
def knowledge_article_page(
    article_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    message: str | None = None,
    error: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "knowledge_article.html",
        _knowledge_article_context(request, db, current_user, article_id, message=message, error=error),
    )


@router.get("/assistant")
def assistant_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    message: str | None = None,
    error: str | None = None,
    chat_id: str = "",
):
    return templates.TemplateResponse(
        request,
        "assistant.html",
        _assistant_context(request, db, current_user, chat_id=chat_id, message=message, error=error),
    )


@router.get("/admin")
def admin_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    message: str | None = None,
    error: str | None = None,
):
    _require_admin_page(current_user)
    return templates.TemplateResponse(request, "admin.html", _admin_context(request, db, current_user, message=message, error=error))


@router.post("/admin/users")
async def create_user_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_page(current_user)
    form = await _read_form(request)
    try:
        UserService.create_user(
            db,
            UserCreate(
                username=form.get("username", ""),
                password=form.get("password", ""),
                role=form.get("role", "employee"),
            ),
        )
    except (HTTPException, ValidationError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else "Проверьте заполнение формы."
        return _redirect("/admin", error=str(detail))
    return _redirect("/admin", message="Пользователь создан.")


@router.post("/admin/onboarding/days")
async def create_day_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_page(current_user)
    form = await _read_form(request)
    try:
        OnboardingService.create_day(
            db,
            OnboardingDayCreate(
                day_number=_parse_day_number(form.get("day_number")),
                title=form.get("title", ""),
                text_content=form.get("text_content", ""),
                media_url=_optional_form_value(form.get("media_url")),
                media_type=_optional_form_value(form.get("media_type")),
            ),
        )
    except (HTTPException, ValidationError, ValueError) as exc:
        if isinstance(exc, HTTPException):
            detail = exc.detail
        elif isinstance(exc, ValueError):
            detail = "Проверьте номер дня."
        else:
            detail = "Проверьте заполнение формы дня."
        return _redirect("/onboarding", error=str(detail))
    return _redirect("/onboarding", message="День адаптации добавлен.")


@router.post("/admin/onboarding/{day_id}/update")
async def update_day_page(
    day_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_page(current_user)
    form = await _read_form(request)
    try:
        current_day = OnboardingService.get_day(db, day_id)
        OnboardingService.update_day(
            db,
            day_id,
            OnboardingDayUpdate(
                day_number=_parse_day_number(form.get("day_number"), fallback=current_day.day_number),
                title=form.get("title", ""),
                text_content=form.get("text_content", ""),
                media_url=_optional_form_value(form.get("media_url")),
                media_type=_optional_form_value(form.get("media_type")),
            ),
        )
    except (HTTPException, ValidationError, ValueError) as exc:
        if isinstance(exc, HTTPException):
            detail = exc.detail
        elif isinstance(exc, ValueError):
            detail = "Проверьте номер дня."
        else:
            detail = "Проверьте заполнение формы дня."
        return _redirect(f"/onboarding/{day_id}", error=str(detail))
    return _redirect(f"/onboarding/{day_id}", message="День адаптации обновлен.")


@router.post("/admin/onboarding/{day_id}/delete")
def delete_day_page(
    day_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_page(current_user)
    try:
        OnboardingService.delete_day(db, day_id)
    except HTTPException as exc:
        return _redirect(f"/onboarding/{day_id}", error=str(exc.detail))
    return _redirect("/onboarding", message="День адаптации удален.")


@router.post("/onboarding/{day_id}/complete")
def complete_day_page(
    day_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        OnboardingService.complete_day(db, current_user, day_id)
    except HTTPException as exc:
        return _redirect("/onboarding", error=str(exc.detail))
    return _redirect("/onboarding", message="День отмечен как завершенный.")


@router.post("/onboarding/{day_id}/complete-async")
def complete_day_async(
    day_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        progress = OnboardingService.complete_day(db, current_user, day_id)
    except HTTPException as exc:
        return JSONResponse({"detail": str(exc.detail)}, status_code=exc.status_code)

    completed_at = _format_datetime(getattr(progress, "completed_at", None))
    return JSONResponse(
        {
            "ok": True,
            "completed_at": completed_at,
            "message": "День отмечен как завершенный.",
        }
    )


@router.post("/admin/knowledge/categories")
async def create_category_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_page(current_user)
    form = await _read_form(request)
    try:
        KnowledgeService.create_category(db, CategoryCreate(name=form.get("name", "")))
    except (HTTPException, ValidationError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else "Введите название категории."
        return _redirect("/knowledge", error=str(detail))
    return _redirect("/knowledge", message="Категория создана.")


@router.post("/admin/knowledge/articles")
async def create_article_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_page(current_user)
    form = await _read_form(request)
    try:
        KnowledgeService.create_article(
            db,
            KnowledgeArticleCreate(
                title=form.get("title", ""),
                text_content=form.get("text_content", ""),
                media_url=_optional_form_value(form.get("media_url")),
                media_type=_optional_form_value(form.get("media_type")),
                category_id=form.get("category_id", ""),
            ),
            current_user,
        )
    except (HTTPException, ValidationError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else "Проверьте поля статьи."
        return _redirect("/knowledge", error=str(detail))
    return _redirect("/knowledge", message="Статья добавлена.")


@router.post("/admin/knowledge/articles/{article_id}/update")
async def update_article_page(
    article_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_page(current_user)
    form = await _read_form(request)
    try:
        KnowledgeService.update_article(
            db,
            article_id,
            KnowledgeArticleUpdate(
                title=form.get("title") or None,
                text_content=form.get("text_content") or None,
                media_url=_optional_form_value(form.get("media_url")),
                media_type=_optional_form_value(form.get("media_type")),
                category_id=form.get("category_id") or None,
            ),
            current_user,
        )
    except (HTTPException, ValidationError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else "Проверьте поля статьи."
        return _redirect(f"/knowledge/{article_id}", error=str(detail))
    return _redirect(f"/knowledge/{article_id}", message="Статья обновлена.")


@router.post("/admin/knowledge/articles/{article_id}/delete")
def delete_article_page(
    article_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_page(current_user)
    try:
        KnowledgeService.delete_article(db, article_id)
    except HTTPException as exc:
        return _redirect(f"/knowledge/{article_id}", error=str(exc.detail))
    return _redirect("/knowledge", message="Статья удалена.")


@router.post("/assistant/ask")
async def ask_chat_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = await _read_form(request)
    question = (form.get("question", "") or "").strip()
    chat_id = form.get("chat_id", "")
    if not question:
        return templates.TemplateResponse(
            request,
            "assistant.html",
            _assistant_context(request, db, current_user, chat_id=chat_id, error="Введите вопрос."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        response = ChatService.ask(
            db=db,
            question=question,
            category_id=None,
            top_k=max(settings.VECTOR_TOP_K, 8),
        )
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "assistant.html",
            _assistant_context(request, db, current_user, chat_id=chat_id, error=str(exc.detail), chat_question=question),
            status_code=exc.status_code,
        )
    session = ChatHistoryService.save_exchange(
        db,
        current_user,
        question=question,
        answer=response.answer,
        session_id=chat_id or None,
    )
    return templates.TemplateResponse(
        request,
        "assistant.html",
        _assistant_context(
            request,
            db,
            current_user,
            chat_id=session.id,
            chat_response=response,
        ),
    )
