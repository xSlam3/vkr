from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.models.user import User
from app.schemas.knowledge import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    KnowledgeArticleCreate,
    KnowledgeArticleRead,
    KnowledgeArticleUpdate,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/categories", response_model=CategoryRead)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return KnowledgeService.create_category(db, payload)


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return KnowledgeService.list_categories(db)


@router.put("/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: str,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return KnowledgeService.update_category(db, category_id, payload)


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    KnowledgeService.delete_category(db, category_id)
    return {"message": "Category deleted"}


@router.post("/articles", response_model=KnowledgeArticleRead)
def create_article(
    payload: KnowledgeArticleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return KnowledgeService.create_article(db, payload, current_user)


@router.get("/articles", response_model=list[KnowledgeArticleRead])
def list_articles(
    search: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return KnowledgeService.list_articles(db, search=search, category_id=category_id)


@router.get("/articles/{article_id}", response_model=KnowledgeArticleRead)
def get_article(
    article_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return KnowledgeService.get_article(db, article_id)


@router.put("/articles/{article_id}", response_model=KnowledgeArticleRead)
def update_article(
    article_id: str,
    payload: KnowledgeArticleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return KnowledgeService.update_article(db, article_id, payload, current_user)


@router.delete("/articles/{article_id}")
def delete_article(
    article_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    KnowledgeService.delete_article(db, article_id)
    return {"message": "Article deleted"}
