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
    database_url = "sqlite://"
    test_engine = create_engine(
        database_url,
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


def test_bootstrap_admin_and_login_returns_jwt(client: TestClient):
    response = _create_user(client, "admin", "123456", "admin")

    assert response.status_code == 200
    login_response = client.post(
        "/users/login",
        json={"username": "admin", "password": "123456"},
    )
    assert login_response.status_code == 200
    payload = login_response.json()
    assert "access_token" in payload
    assert payload["token_type"] == "bearer"


def test_first_user_must_be_admin(client: TestClient):
    response = _create_user(client, "employee1", "123456", "employee")

    assert response.status_code == 400
    assert response.json()["detail"] == "First user must have admin role"


def test_me_returns_current_user(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "admin"


def test_admin_only_routes_are_protected(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")
    _create_user(client, "employee1", "123456", "employee", token=admin_token)
    employee_token = _login(client, "employee1", "123456")

    list_as_employee = client.get(
        "/users/",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert list_as_employee.status_code == 403

    create_as_employee = _create_user(client, "employee2", "123456", "employee", token=employee_token)
    assert create_as_employee.status_code == 403

    list_as_admin = client.get(
        "/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_as_admin.status_code == 200
    assert len(list_as_admin.json()) == 2


def test_admin_can_delete_user(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")
    employee_response = _create_user(client, "employee1", "123456", "employee", token=admin_token)
    employee_id = employee_response.json()["id"]

    delete_response = client.delete(
        f"/users/{employee_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_response.status_code == 200

    list_response = client.get(
        "/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert len(list_response.json()) == 1


def test_admin_can_update_user(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")
    employee_response = _create_user(client, "employee1", "123456", "employee", token=admin_token)
    employee_id = employee_response.json()["id"]

    update_response = client.put(
        f"/users/{employee_id}",
        json={
            "username": "employee.updated",
            "role": "admin",
            "password": "654321",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["username"] == "employee.updated"
    assert update_response.json()["role"].lower().endswith("admin")

    login_with_old_password = client.post(
        "/users/login",
        json={"username": "employee.updated", "password": "123456"},
    )
    assert login_with_old_password.status_code == 401

    login_with_new_password = client.post(
        "/users/login",
        json={"username": "employee.updated", "password": "654321"},
    )
    assert login_with_new_password.status_code == 200


def test_login_fail(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    response = client.post("/users/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
