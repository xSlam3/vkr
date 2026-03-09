from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.knowledge import Category, KnowledgeArticle


class KnowledgeRepository:
    @staticmethod
    def create_category(db: Session, name: str) -> Category:
        category = Category(name=name)
        db.add(category)
        db.commit()
        db.refresh(category)
        return category

    @staticmethod
    def get_category_by_id(db: Session, category_id: str) -> Category | None:
        return db.query(Category).filter(Category.id == category_id).first()

    @staticmethod
    def get_category_by_name(db: Session, name: str) -> Category | None:
        return db.query(Category).filter(Category.name == name).first()

    @staticmethod
    def list_categories(db: Session) -> list[Category]:
        return db.query(Category).order_by(Category.name.asc()).all()

    @staticmethod
    def update_category(db: Session, category: Category, name: str) -> Category:
        category.name = name
        db.commit()
        db.refresh(category)
        return category

    @staticmethod
    def delete_category(db: Session, category: Category) -> None:
        db.delete(category)
        db.commit()

    @staticmethod
    def count_articles_in_category(db: Session, category_id: str) -> int:
        return db.query(KnowledgeArticle).filter(KnowledgeArticle.category_id == category_id).count()

    @staticmethod
    def create_article(db: Session, data: dict) -> KnowledgeArticle:
        article = KnowledgeArticle(**data)
        db.add(article)
        db.commit()
        db.refresh(article)
        return article

    @staticmethod
    def get_article_by_id(db: Session, article_id: str) -> KnowledgeArticle | None:
        return db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id).first()

    @staticmethod
    def list_articles(
        db: Session,
        search: str | None = None,
        category_id: str | None = None,
    ) -> list[KnowledgeArticle]:
        query = db.query(KnowledgeArticle)
        if category_id:
            query = query.filter(KnowledgeArticle.category_id == category_id)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    KnowledgeArticle.title.ilike(pattern),
                    KnowledgeArticle.text_content.ilike(pattern),
                )
            )
        return query.order_by(KnowledgeArticle.updated_at.desc()).all()

    @staticmethod
    def update_article(db: Session, article: KnowledgeArticle, data: dict) -> KnowledgeArticle:
        for key, value in data.items():
            setattr(article, key, value)
        db.commit()
        db.refresh(article)
        return article

    @staticmethod
    def delete_article(db: Session, article: KnowledgeArticle) -> None:
        db.delete(article)
        db.commit()
