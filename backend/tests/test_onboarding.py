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


def _create_day(client: TestClient, token: str, day_number: int, title: str):
    return client.post(
        "/onboarding/days",
        json={
            "day_number": day_number,
            "title": title,
            "text_content": f"{title} content",
            "media_url": None,
            "media_type": None,
        },
        headers={"Authorization": f"Bearer {token}"},
    )


def test_admin_can_manage_days(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")

    create_response = _create_day(client, admin_token, 1, "Day 1")
    assert create_response.status_code == 200
    day_id = create_response.json()["id"]

    update_response = client.put(
        f"/onboarding/days/{day_id}",
        json={"title": "Updated Day 1"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Updated Day 1"

    list_response = client.get(
        "/onboarding/days",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    delete_response = client.delete(
        f"/onboarding/days/{day_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_response.status_code == 200


def test_employee_cannot_manage_days(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")
    _create_day(client, admin_token, 1, "Day 1")

    _create_user(client, "employee1", "123456", "employee", token=admin_token)
    employee_token = _login(client, "employee1", "123456")

    create_response = _create_day(client, employee_token, 2, "Day 2")
    assert create_response.status_code == 403

    list_response = client.get(
        "/onboarding/days",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert list_response.status_code == 200
    day_id = list_response.json()[0]["id"]

    update_response = client.put(
        f"/onboarding/days/{day_id}",
        json={"title": "Should Fail"},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert update_response.status_code == 403

    delete_response = client.delete(
        f"/onboarding/days/{day_id}",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert delete_response.status_code == 403


def test_employee_can_complete_day_and_see_progress(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")
    day1 = _create_day(client, admin_token, 1, "Day 1")
    _create_day(client, admin_token, 2, "Day 2")

    _create_user(client, "employee1", "123456", "employee", token=admin_token)
    employee_token = _login(client, "employee1", "123456")

    initial_me = client.get(
        "/onboarding/me",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert initial_me.status_code == 200
    assert len(initial_me.json()) == 2
    assert initial_me.json()[0]["completed"] is False

    complete_response = client.post(
        f"/onboarding/days/{day1.json()['id']}/complete",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["completed"] is True

    updated_me = client.get(
        "/onboarding/me",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert updated_me.status_code == 200
    by_day_number = {item["day_number"]: item for item in updated_me.json()}
    assert by_day_number[1]["completed"] is True
    assert by_day_number[1]["completed_at"] is not None
    assert by_day_number[2]["completed"] is False


def test_day_number_must_be_unique(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")

    first = _create_day(client, admin_token, 1, "Day 1")
    assert first.status_code == 200

    duplicate = _create_day(client, admin_token, 1, "Duplicate Day 1")
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "Day number already exists"


def test_web_update_day_accepts_none_like_media_values_when_renaming(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")

    created = _create_day(client, admin_token, 1, "Day 1")
    day_id = created.json()["id"]

    login_response = client.post(
        "/login",
        data={"username": "admin", "password": "123456"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303

    update_response = client.post(
        f"/admin/onboarding/{day_id}/update",
        data={
            "day_number": "1",
            "title": "Updated Day 1",
            "text_content": "Day 1 content",
            "media_url": "None",
            "media_type": "None",
        },
        cookies=login_response.cookies,
        follow_redirects=False,
    )
    assert update_response.status_code == 303
    assert "/onboarding/" in update_response.headers["location"]
    assert "error=" not in update_response.headers["location"]

    updated_day = client.get(
        f"/onboarding/days/{day_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert updated_day.status_code == 200
    assert updated_day.json()["title"] == "Updated Day 1"
    assert updated_day.json()["media_url"] is None
    assert updated_day.json()["media_type"] is None


def test_web_update_day_keeps_current_day_number_when_form_omits_it(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")

    created = _create_day(client, admin_token, 1, "Day 1")
    day_id = created.json()["id"]

    login_response = client.post(
        "/login",
        data={"username": "admin", "password": "123456"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303

    update_response = client.post(
        f"/admin/onboarding/{day_id}/update",
        data={
            "day_number": "",
            "title": "Renamed Day 1",
            "text_content": "Day 1 content",
            "media_url": "",
            "media_type": "",
        },
        cookies=login_response.cookies,
        follow_redirects=False,
    )
    assert update_response.status_code == 303
    assert "/onboarding/" in update_response.headers["location"]
    assert "error=" not in update_response.headers["location"]

    updated_day = client.get(
        f"/onboarding/days/{day_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert updated_day.status_code == 200
    assert updated_day.json()["title"] == "Renamed Day 1"
    assert updated_day.json()["day_number"] == 1


def test_web_update_day_accepts_human_readable_day_number_value(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    admin_token = _login(client, "admin", "123456")

    created = _create_day(client, admin_token, 1, "Day 1")
    day_id = created.json()["id"]

    login_response = client.post(
        "/login",
        data={"username": "admin", "password": "123456"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303

    update_response = client.post(
        f"/admin/onboarding/{day_id}/update",
        data={
            "day_number": "День 1",
            "title": "Renamed Day Human Value",
            "text_content": "Day 1 content",
            "media_url": "",
            "media_type": "",
        },
        cookies=login_response.cookies,
        follow_redirects=False,
    )
    assert update_response.status_code == 303
    assert "/onboarding/" in update_response.headers["location"]
    assert "error=" not in update_response.headers["location"]

    updated_day = client.get(
        f"/onboarding/days/{day_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert updated_day.status_code == 200
    assert updated_day.json()["title"] == "Renamed Day Human Value"
    assert updated_day.json()["day_number"] == 1


def test_onboarding_requires_auth(client: TestClient):
    _create_user(client, "admin", "123456", "admin")

    list_response = client.get("/onboarding/days")
    me_response = client.get("/onboarding/me")

    assert list_response.status_code == 401
    assert me_response.status_code == 401
