import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.services.vector_service import RetrievedChunk, VectorService


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


def test_chat_requires_auth(client: TestClient):
    response = client.post("/chat/", json={"question": "hello"})
    assert response.status_code == 401


def test_chat_returns_not_found_without_context(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")

    monkeypatch.setattr(VectorService, "search", classmethod(lambda cls, query, top_k=None, category_id=None: []))
    response = client.post(
        "/chat/",
        json={"question": "как полировать кольцо?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_context"] is False
    assert payload["sources"] == []


def test_chat_uses_vector_context(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")

    chunks = [
        RetrievedChunk(
            article_id="a1",
            title="Care",
            category_id="c1",
            chunk_index=0,
            text="Use soft brush and warm water.",
            score=0.9,
        )
    ]
    monkeypatch.setattr(
        VectorService,
        "search",
        classmethod(lambda cls, query, top_k=None, category_id=None: chunks),
    )
    monkeypatch.setattr(settings, "CHAT_USE_LLM", False)

    response = client.post(
        "/chat/",
        json={"question": "как чистить кольцо?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_context"] is True
    assert "soft brush" in payload["answer"].lower()
    assert payload["sources"][0]["article_id"] == "a1"


def test_chat_can_use_llm(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")

    chunks = [
        RetrievedChunk(
            article_id="a1",
            title="Care",
            category_id="c1",
            chunk_index=0,
            text="Use soft brush.",
            score=0.95,
        )
    ]
    monkeypatch.setattr(
        VectorService,
        "search",
        classmethod(lambda cls, query, top_k=None, category_id=None: chunks),
    )
    monkeypatch.setattr(settings, "CHAT_USE_LLM", True)
    monkeypatch.setattr(settings, "LLM_API_URL", "http://llm.local/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "local-model")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Ответ из LLM"}}]}

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeResponse())

    response = client.post(
        "/chat/",
        json={"question": "что делать?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Ответ из LLM"
