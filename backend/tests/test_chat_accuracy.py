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


def test_chat_strips_non_russian_artifacts_from_llm_answer(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Metals")
    article = _create_article(
        client,
        token,
        category["id"],
        "Пробы",
        "<p>В сплаве 585 содержится 585 частей золота на 1000 частей сплава.</p>",
    )

    chunks = [
        RetrievedChunk(
            article_id=article["id"],
            title="Пробы",
            category_id=category["id"],
            chunk_index=0,
            text="В сплаве 585 содержится 585 частей золота на 1000 частей сплава.",
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
            return {"choices": [{"message": {"content": "Проба 585 означает 58.5% золота 含金量约58.5%。"}}]}

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: FakeResponse())

    response = client.post(
        "/chat/",
        json={"question": "Что значит 585?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "含金量" not in answer
    assert "Проба 585" in answer


def test_chat_prefers_stone_evaluation_article_for_size_price_question(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Stones")
    explanation = _create_article(
        client,
        token,
        category["id"],
        "Как объяснять клиенту пробу, камень и цену",
        "<p>Цена зависит от металла, вставок и сложности модели.</p><p>Камень объясняется через его вид и характеристики.</p>",
    )
    evaluation = _create_article(
        client,
        token,
        category["id"],
        "Оценка камней",
        "<p>Масса измеряется в каратах.</p><p>Оценивать камень только по размеру нельзя.</p>",
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
    assert payload["sources"][0]["article_id"] == evaluation["id"]
    assert payload["sources"][0]["article_id"] != explanation["id"]


def test_chat_prefers_probe_article_over_misleading_vector_matches(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Metals")
    probes = _create_article(
        client,
        token,
        category["id"],
        "Пробы",
        "<p>Для серебра встречаются пробы 800, 830, 875, 925, 960 и 999.</p>",
    )
    metals = _create_article(
        client,
        token,
        category["id"],
        "Драгоценные металлы",
        "<p>Серебро относится к драгоценным металлам.</p>",
    )
    hallmarks = _create_article(
        client,
        token,
        category["id"],
        "Клейма и маркировка",
        "<p>На изделиях ставят пробирные клейма.</p>",
    )

    chunks = [
        RetrievedChunk(
            article_id=metals["id"],
            title="Драгоценные металлы",
            category_id=category["id"],
            chunk_index=0,
            text="Серебро относится к драгоценным металлам.",
            score=0.38,
        ),
        RetrievedChunk(
            article_id=hallmarks["id"],
            title="Клейма и маркировка",
            category_id=category["id"],
            chunk_index=0,
            text="На изделиях ставят пробирные клейма.",
            score=0.26,
        ),
    ]
    monkeypatch.setattr(
        VectorService,
        "search",
        classmethod(lambda cls, query, top_k=None, category_id=None: chunks),
    )
    monkeypatch.setattr(settings, "CHAT_USE_LLM", False)

    response = client.post(
        "/chat/",
        json={"question": "какие есть пробы серебра"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"][0]["article_id"] == probes["id"]
    assert "925" in payload["answer"]


def test_chat_prefers_showcase_article_for_expensive_ring_display_question(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Sales floor")
    showcase = _create_article(
        client,
        token,
        category["id"],
        "Выкладка ювелирных изделий и зонирование магазина",
        (
            "<p>В горячие зоны ставят ключевые модели и дорогие изделия.</p>"
            "<p>Дорогие изделия размещаются выше остальных, ближе к центру или на уровне глаз.</p>"
        ),
    )
    metals = _create_article(
        client,
        token,
        category["id"],
        "Драгоценные металлы",
        "<p>Золото, серебро и платина относятся к драгоценным металлам.</p>",
    )

    chunks = [
        RetrievedChunk(
            article_id=metals["id"],
            title="Драгоценные металлы",
            category_id=category["id"],
            chunk_index=0,
            text="Золото, серебро и платина относятся к драгоценным металлам.",
            score=0.39,
        ),
    ]
    monkeypatch.setattr(
        VectorService,
        "search",
        classmethod(lambda cls, query, top_k=None, category_id=None: chunks),
    )
    monkeypatch.setattr(settings, "CHAT_USE_LLM", False)

    response = client.post(
        "/chat/",
        json={"question": "в какой части витрины выложить дорогое кольцо"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"][0]["article_id"] == showcase["id"]
    assert "центру" in payload["answer"].lower() or "уровне глаз" in payload["answer"].lower()


def test_chat_fallback_keeps_showcase_answer_substantive_for_rich_article(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")
    category = _create_category(client, token, "Sales floor")

    article = _create_article(
        client,
        token,
        category["id"],
        "Выкладка ювелирных изделий и зонирование магазина",
        (
            "<p>Выкладка — это инструмент, который управляет<br>вниманием покупателя и напрямую влияет на продажи.</p>"
            "<p>Основные зоны:</p>"
            "<p>●</p><p>зона дорогих украшений — формирует имидж</p>"
            "<p>●</p><p>ценовой сегмент</p>"
            "<p>Дорогие изделия размещаются выше остальных,<br>ближе к центру или на уровне глаз.</p>"
        ),
    )

    monkeypatch.setattr(VectorService, "search", classmethod(lambda cls, query, top_k=None, category_id=None: []))
    monkeypatch.setattr(settings, "CHAT_USE_LLM", False)

    response = client.post(
        "/chat/",
        json={"question": "где расположить на выкладке дорогое кольцо"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"][0]["article_id"] == article["id"]
    assert len(payload["sources"]) == 1
    assert "ближе к центру" in payload["answer"].lower() or "на уровне глаз" in payload["answer"].lower()
    assert "ценовой сегмент" not in payload["answer"].lower()
