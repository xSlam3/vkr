import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db.base import Base
from app.main import app
from app.services.vector_service import VectorService


@pytest.fixture()
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _create_user(client: TestClient, username: str, password: str, role: str, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/users/",
        json={"username": username, "password": password, "role": role},
        headers=headers,
    )


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/users/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_knowledge_triggers_vector_index_hooks(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    headers = {"Authorization": f"Bearer {token}"}

    upsert_calls = []
    delete_calls = []

    monkeypatch.setattr(
        VectorService,
        "upsert_article",
        classmethod(
            lambda cls, article_id, title, text_content, category_id: upsert_calls.append(
                {
                    "article_id": article_id,
                    "title": title,
                    "text_content": text_content,
                    "category_id": category_id,
                }
            )
        ),
    )
    monkeypatch.setattr(
        VectorService,
        "delete_article",
        classmethod(lambda cls, article_id: delete_calls.append(article_id)),
    )

    category = client.post("/knowledge/categories", json={"name": "Sales"}, headers=headers)
    category_id = category.json()["id"]

    created = client.post(
        "/knowledge/articles",
        json={
            "title": "Greeting",
            "text_content": "Smile and introduce yourself.",
            "media_url": None,
            "media_type": None,
            "category_id": category_id,
        },
        headers=headers,
    )
    assert created.status_code == 200
    article_id = created.json()["id"]

    updated = client.put(
        f"/knowledge/articles/{article_id}",
        json={"text_content": "Smile, introduce yourself, ask preferences."},
        headers=headers,
    )
    assert updated.status_code == 200

    deleted = client.delete(f"/knowledge/articles/{article_id}", headers=headers)
    assert deleted.status_code == 200

    assert len(upsert_calls) == 2
    assert upsert_calls[0]["article_id"] == article_id
    assert upsert_calls[1]["text_content"].startswith("Smile, introduce")
    assert delete_calls == [article_id]
