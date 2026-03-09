import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db.base import Base
from app.main import app


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
    return client.post(
        "/knowledge/categories",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )


def _create_article(
    client: TestClient,
    token: str,
    category_id: str,
    title: str,
    text_content: str,
):
    return client.post(
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


def test_category_crud_and_duplicate_name(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")

    create = _create_category(client, admin_token, "Sales")
    assert create.status_code == 200
    category_id = create.json()["id"]

    duplicate = _create_category(client, admin_token, "Sales")
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "Category name already exists"

    update = client.put(
        f"/knowledge/categories/{category_id}",
        json={"name": "Store Rules"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Store Rules"

    list_response = client.get(
        "/knowledge/categories",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_article_crud_search_filter_and_last_edited_by(client: TestClient):
    _create_user(client, "admin1", "123456", "admin")
    admin1_token = _login(client, "admin1", "123456")
    admin1_id = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {admin1_token}"},
    ).json()["id"]

    _create_user(client, "admin2", "123456", "admin", token=admin1_token)
    admin2_token = _login(client, "admin2", "123456")
    admin2_id = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {admin2_token}"},
    ).json()["id"]

    category = _create_category(client, admin1_token, "Gemstones")
    category_id = category.json()["id"]

    article = _create_article(
        client,
        admin1_token,
        category_id,
        "How to clean rings",
        "Use soft brush and warm water",
    )
    assert article.status_code == 200
    article_id = article.json()["id"]
    assert article.json()["last_edited_by"] == admin1_id

    list_response = client.get(
        "/knowledge/articles",
        headers={"Authorization": f"Bearer {admin1_token}"},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    search_response = client.get(
        "/knowledge/articles?search=clean",
        headers={"Authorization": f"Bearer {admin1_token}"},
    )
    assert search_response.status_code == 200
    assert len(search_response.json()) == 1

    filter_response = client.get(
        f"/knowledge/articles?category_id={category_id}",
        headers={"Authorization": f"Bearer {admin1_token}"},
    )
    assert filter_response.status_code == 200
    assert len(filter_response.json()) == 1

    update_response = client.put(
        f"/knowledge/articles/{article_id}",
        json={"title": "Updated title"},
        headers={"Authorization": f"Bearer {admin2_token}"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Updated title"
    assert update_response.json()["last_edited_by"] == admin2_id

    get_response = client.get(
        f"/knowledge/articles/{article_id}",
        headers={"Authorization": f"Bearer {admin1_token}"},
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == article_id


def test_cannot_delete_category_with_articles(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")

    category = _create_category(client, admin_token, "Policies")
    category_id = category.json()["id"]
    article = _create_article(client, admin_token, category_id, "Refund policy", "No refunds")
    article_id = article.json()["id"]

    delete_category_fail = client.delete(
        f"/knowledge/categories/{category_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_category_fail.status_code == 400
    assert delete_category_fail.json()["detail"] == "Cannot delete category with existing articles"

    delete_article = client.delete(
        f"/knowledge/articles/{article_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_article.status_code == 200

    delete_category = client.delete(
        f"/knowledge/categories/{category_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_category.status_code == 200


def test_employee_has_read_only_access(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")
    category = _create_category(client, admin_token, "Products")
    category_id = category.json()["id"]
    _create_article(client, admin_token, category_id, "Product sizing", "Use ring size chart")

    _create_user(client, "employee", "123456", "employee", token=admin_token)
    employee_token = _login(client, "employee", "123456")

    read_categories = client.get(
        "/knowledge/categories",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert read_categories.status_code == 200

    read_articles = client.get(
        "/knowledge/articles",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert read_articles.status_code == 200

    write_category = _create_category(client, employee_token, "Should fail")
    assert write_category.status_code == 403

    write_article = _create_article(
        client,
        employee_token,
        category_id,
        "Should fail",
        "No write access",
    )
    assert write_article.status_code == 403


def test_knowledge_requires_auth(client: TestClient):
    _create_user(client, "admin", "123456", "admin")

    categories = client.get("/knowledge/categories")
    articles = client.get("/knowledge/articles")

    assert categories.status_code == 401
    assert articles.status_code == 401
