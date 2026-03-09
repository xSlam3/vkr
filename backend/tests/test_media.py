import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.services.s3_service import S3Service


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


class FakeS3Client:
    def generate_presigned_post(self, Bucket, Key, Fields, Conditions, ExpiresIn):
        return {
            "url": "https://upload.example.com",
            "fields": {
                "key": Key,
                "Content-Type": Fields["Content-Type"],
                "policy": "test-policy",
            },
        }

    def generate_presigned_url(self, client_method, Params, ExpiresIn):
        return f"https://download.example.com/{Params['Key']}?expires={ExpiresIn}"


def test_media_requires_auth(client: TestClient):
    upload = client.post(
        "/media/presign-upload",
        json={
            "filename": "pic.png",
            "content_type": "image/png",
            "scope": "knowledge",
        },
    )
    download = client.get("/media/presign-download?key=knowledge/a.png")

    assert upload.status_code == 401
    assert download.status_code == 401


def test_presign_upload_success(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")

    monkeypatch.setattr(settings, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    monkeypatch.setattr(settings, "S3_PRESIGNED_EXPIRES_SECONDS", 300)
    monkeypatch.setattr(S3Service, "_get_client", staticmethod(lambda: FakeS3Client()))

    response = client.post(
        "/media/presign-upload",
        json={
            "filename": "training.png",
            "content_type": "image/png",
            "scope": "knowledge",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"] == "https://upload.example.com"
    assert payload["key"].startswith("knowledge/")
    assert payload["key"].endswith(".png")
    assert payload["object_url"] == f"http://127.0.0.1:9000/test-bucket/{payload['key']}"
    assert payload["fields"]["Content-Type"] == "image/png"
    assert payload["expires_in"] == 300


def test_presign_upload_rejects_non_media_content_type(client: TestClient):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")

    response = client.post(
        "/media/presign-upload",
        json={
            "filename": "manual.pdf",
            "content_type": "application/pdf",
            "scope": "knowledge",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only image/* and video/* content types are allowed"


def test_presign_download_success_and_invalid_key(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _create_user(client, "admin", "123456", "admin")
    token = _login(client, "admin", "123456")

    monkeypatch.setattr(settings, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(settings, "S3_PRESIGNED_EXPIRES_SECONDS", 600)
    monkeypatch.setattr(S3Service, "_get_client", staticmethod(lambda: FakeS3Client()))

    ok = client.get(
        "/media/presign-download?key=knowledge/video.mp4",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200
    assert "knowledge/video.mp4" in ok.json()["url"]
    assert ok.json()["expires_in"] == 600

    bad = client.get(
        "/media/presign-download?key=../secret.txt",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "Invalid object key"
