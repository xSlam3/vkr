from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.knowledge_repo import KnowledgeRepository
from app.schemas.knowledge import (
    CategoryCreate,
    CategoryUpdate,
    KnowledgeArticleCreate,
    KnowledgeArticleUpdate,
)
from app.services.rich_text_service import RichTextService
from app.services.vector_service import VectorService


class KnowledgeService:
    @staticmethod
    def create_category(db: Session, payload: CategoryCreate):
        if KnowledgeRepository.get_category_by_name(db, payload.name):
            raise HTTPException(status_code=400, detail="Category name already exists")
        return KnowledgeRepository.create_category(db, payload.name)

    @staticmethod
    def list_categories(db: Session):
        return KnowledgeRepository.list_categories(db)

    @staticmethod
    def get_category(db: Session, category_id: str):
        category = KnowledgeRepository.get_category_by_id(db, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        return category

    @staticmethod
    def update_category(db: Session, category_id: str, payload: CategoryUpdate):
        category = KnowledgeService.get_category(db, category_id)
        existing = KnowledgeRepository.get_category_by_name(db, payload.name)
        if existing and existing.id != category_id:
            raise HTTPException(status_code=400, detail="Category name already exists")
        return KnowledgeRepository.update_category(db, category, payload.name)

    @staticmethod
    def delete_category(db: Session, category_id: str) -> None:
        category = KnowledgeService.get_category(db, category_id)
        article_count = KnowledgeRepository.count_articles_in_category(db, category_id)
        if article_count > 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete category with existing articles",
            )
        KnowledgeRepository.delete_category(db, category)

    @staticmethod
    def create_article(db: Session, payload: KnowledgeArticleCreate, current_user: User):
        category = KnowledgeRepository.get_category_by_id(db, payload.category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        data = payload.model_dump()
        data["text_content"] = RichTextService.sanitize(data["text_content"])
        data["last_edited_by"] = current_user.id
        article = KnowledgeRepository.create_article(db, data)
        VectorService.upsert_article(
            article_id=article.id,
            title=article.title,
            text_content=article.text_content,
            category_id=article.category_id,
        )
        return article

    @staticmethod
    def list_articles(db: Session, search: str | None = None, category_id: str | None = None):
        if category_id:
            category = KnowledgeRepository.get_category_by_id(db, category_id)
            if not category:
                raise HTTPException(status_code=404, detail="Category not found")
        return KnowledgeRepository.list_articles(db, search=search, category_id=category_id)

    @staticmethod
    def get_article(db: Session, article_id: str):
        article = KnowledgeRepository.get_article_by_id(db, article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        return article

    @staticmethod
    def update_article(
        db: Session,
        article_id: str,
        payload: KnowledgeArticleUpdate,
        current_user: User,
    ):
        article = KnowledgeService.get_article(db, article_id)
        update_data = payload.model_dump(exclude_unset=True)

        new_category_id = update_data.get("category_id")
        if new_category_id:
            category = KnowledgeRepository.get_category_by_id(db, new_category_id)
            if not category:
                raise HTTPException(status_code=404, detail="Category not found")

        if not update_data:
            return article

        if "text_content" in update_data:
            update_data["text_content"] = RichTextService.sanitize(update_data["text_content"])

        update_data["last_edited_by"] = current_user.id
        updated_article = KnowledgeRepository.update_article(db, article, update_data)
        VectorService.upsert_article(
            article_id=updated_article.id,
            title=updated_article.title,
            text_content=updated_article.text_content,
            category_id=updated_article.category_id,
        )
        return updated_article

    @staticmethod
    def delete_article(db: Session, article_id: str) -> None:
        article = KnowledgeService.get_article(db, article_id)
        KnowledgeRepository.delete_article(db, article)
        VectorService.delete_article(article_id)
