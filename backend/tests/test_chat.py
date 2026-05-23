import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.services.chat_service import ChatService
from app.services.vector_service import RetrievedChunk, VectorService
from app.web import _format_chat_message


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


def _create_category(client: TestClient, token: str, name: str):
    response = client.post(
        "/knowledge/categories",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()


def _create_article(
    client: TestClient,
    token: str,
    category_id: str,
    title: str,
    text_content: str,
):
    response = client.post(
        "/knowledge/articles",
        json={
            "title": title,
            "text_content": text_content,
            "media_url": None,
            "media_type": None,
            "category_id": category_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()


def test_chat_requires_auth(client: TestClient):
    response = client.post("/chat/", json={"question": "hello"})
    assert response.status_code == 401


def test_format_chat_message_renders_bold_markdown_safely():
    formatted = _format_chat_message("Вступление\n\n**Краткий ответ:**\n<script>alert(1)</script>")

    assert "<strong>Краткий ответ:</strong>" in formatted
    assert "**" not in formatted
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in formatted


def test_chat_returns_not_found_without_context(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")

    monkeypatch.setattr(VectorService, "search", classmethod(lambda cls, query, top_k=None, category_id=None: []))
    response = client.post(
        "/chat/",
        json={"question": "how to polish a ring?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_context"] is False
    assert payload["sources"] == []


def test_chat_uses_vector_context(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Care")
    article = _create_article(
        client,
        token,
        category["id"],
        "Care",
        "<p>Use soft brush and warm water.</p><p>Store separately.</p>",
    )

    chunks = [
        RetrievedChunk(
            article_id=article["id"],
            title="Care",
            category_id=category["id"],
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
        json={"question": "how to clean a ring?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_context"] is True
    assert "soft brush" in payload["answer"].lower()
    assert payload["sources"][0]["article_id"] == article["id"]


def test_chat_fallback_returns_relevant_fragments_for_table_question(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Metals")
    article = _create_article(
        client,
        token,
        category["id"],
        "Precious metals",
        (
            "<p>Physical properties.</p>"
            "<table><tbody>"
            "<tr><th>Metal</th><th>Density</th><th>Mohs hardness</th></tr>"
            "<tr><td>Gold</td><td>19320</td><td>2.5</td></tr>"
            "<tr><td>Silver</td><td>10500</td><td>2.7</td></tr>"
            "</tbody></table>"
        ),
    )

    chunks = [
        RetrievedChunk(
            article_id=article["id"],
            title="Precious metals",
            category_id=category["id"],
            chunk_index=0,
            text="Gold | 19320 | 2.5",
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
        json={"question": "density of gold and mohs hardness"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "19320" in answer
    assert "2.5" in answer
    assert "Gold" in answer


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
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "LLM answer"}}]}

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeResponse())

    response = client.post(
        "/chat/",
        json={"question": "what should I do?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "LLM answer"


def test_chat_returns_openrouter_error_instead_of_fallback(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Metals")
    article = _create_article(
        client,
        token,
        category["id"],
        "Precious metals",
        "<p>Gold has density 19320 and Mohs hardness 2.5.</p>",
    )

    chunks = [
        RetrievedChunk(
            article_id=article["id"],
            title="Precious metals",
            category_id=category["id"],
            chunk_index=0,
            text="Gold has density 19320 and Mohs hardness 2.5.",
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
        status_code = 429
        text = "rate limited"

        def json(self):
            return {
                "error": {
                    "message": "Provider returned error",
                    "metadata": {
                        "raw": "model is temporarily rate-limited upstream",
                    },
                }
            }

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeResponse())

    response = client.post(
        "/chat/",
        json={"question": "density of gold"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "OpenRouter" in answer
    assert "rate limit" in answer.lower()
    assert "19320" not in answer


def test_chat_sends_full_article_to_llm(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Care")
    article = _create_article(
        client,
        token,
        category["id"],
        "Ring care",
        "<p>Use a soft brush.</p><p>Do not use acids or chlorine.</p>",
    )

    chunks = [
        RetrievedChunk(
            article_id=article["id"],
            title="Ring care",
            category_id=category["id"],
            chunk_index=0,
            text="Use a soft brush.",
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

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "Use a soft brush and avoid acids."}}]}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["payload"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("httpx.post", fake_post)

    response = client.post(
        "/chat/",
        json={"question": "How should I clean a ring?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Use a soft brush and avoid acids."
    assert "Do not use acids or chlorine." in captured["payload"]["messages"][1]["content"]
    assert "[Статья 1] Ring care" in captured["payload"]["messages"][1]["content"]


def test_chat_passes_top_k_and_category_to_service(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")

    captured = {}

    def fake_ask(db, question: str, top_k: int | None = None, category_id: str | None = None):
        captured["question"] = question
        captured["top_k"] = top_k
        captured["category_id"] = category_id
        captured["has_db"] = db is not None
        return {
            "answer": "ok",
            "sources": [],
            "used_context": False,
        }

    monkeypatch.setattr(ChatService, "ask", staticmethod(fake_ask))

    response = client.post(
        "/chat/",
        json={
            "question": "where is care guide",
            "top_k": 2,
            "category_id": "cat-1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert captured == {
        "has_db": True,
        "question": "where is care guide",
        "top_k": 2,
        "category_id": "cat-1",
    }


def test_chat_handles_naive_probe_question(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Metals")
    article = _create_article(
        client,
        token,
        category["id"],
        "Пробы",
        (
            "<p>Проба означает количество драгоценного металла в одной тысяче частей сплава.</p>"
            "<p>Для золота часто встречается проба 585.</p>"
        ),
    )

    monkeypatch.setattr(VectorService, "search", classmethod(lambda cls, query, top_k=None, category_id=None: []))
    monkeypatch.setattr(settings, "CHAT_USE_LLM", False)

    response = client.post(
        "/chat/",
        json={"question": "Что значит 585 на кольце простыми словами?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"][0]["article_id"] == article["id"]
    assert "проба" in payload["answer"].lower()


def test_chat_handles_naive_imitation_question(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Stones")
    article = _create_article(
        client,
        token,
        category["id"],
        "Искусственные вставки и имитации",
        (
            "<p>Имитация воспроизводит внешний эффект природного камня.</p>"
            "<p>Синтетический камень выращивается как материал, а не только копирует внешний вид.</p>"
        ),
    )

    monkeypatch.setattr(VectorService, "search", classmethod(lambda cls, query, top_k=None, category_id=None: []))
    monkeypatch.setattr(settings, "CHAT_USE_LLM", False)

    response = client.post(
        "/chat/",
        json={"question": "Чем синтетический камень отличается от подделки?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"][0]["article_id"] == article["id"]
    assert "имитац" in payload["answer"].lower() or "синтет" in payload["answer"].lower()


def test_chat_handles_naive_stone_value_question(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Stones")
    article = _create_article(
        client,
        token,
        category["id"],
        "Оценка камней",
        (
            "<p>Оценка камней строится по массе, цветности, чистоте и качеству огранки.</p>"
            "<p>Оценивать камень только по размеру нельзя.</p>"
        ),
    )

    monkeypatch.setattr(VectorService, "search", classmethod(lambda cls, query, top_k=None, category_id=None: []))
    monkeypatch.setattr(settings, "CHAT_USE_LLM", False)

    response = client.post(
        "/chat/",
        json={"question": "Если камень просто большой, это значит он дорогой?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"][0]["article_id"] == article["id"]
    assert "размер" in payload["answer"].lower()
