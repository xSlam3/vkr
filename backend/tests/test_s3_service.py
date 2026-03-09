import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.s3_service import S3Service


def test_get_client_uses_path_style_when_enabled(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_boto3_client(service_name, **kwargs):
        captured["service_name"] = service_name
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("boto3.client", fake_boto3_client)
    monkeypatch.setattr(settings, "S3_BUCKET", "local-bucket")
    monkeypatch.setattr(settings, "S3_REGION", "us-east-1")
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "minioadmin")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "minioadmin")
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    monkeypatch.setattr(settings, "S3_FORCE_PATH_STYLE", True)

    S3Service._get_client()

    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] == "http://127.0.0.1:9000"
    assert captured["config"].s3["addressing_style"] == "path"


def test_get_client_uses_auto_style_when_disabled(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_boto3_client(service_name, **kwargs):
        captured["service_name"] = service_name
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("boto3.client", fake_boto3_client)
    monkeypatch.setattr(settings, "S3_BUCKET", "prod-bucket")
    monkeypatch.setattr(settings, "S3_REGION", "us-east-1")
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "")
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "")
    monkeypatch.setattr(settings, "S3_FORCE_PATH_STYLE", False)

    S3Service._get_client()

    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] is None
    assert captured["config"].s3["addressing_style"] == "auto"


def test_get_client_requires_bucket(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "S3_BUCKET", "")
    with pytest.raises(HTTPException) as exc:
        S3Service._get_client()
    assert exc.value.status_code == 500
    assert exc.value.detail == "S3_BUCKET is not configured"


def test_object_url_for_endpoint_and_aws(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "S3_BUCKET", "jewelry-media")
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "http://127.0.0.1:9000/")
    local_url = S3Service.object_url("knowledge/test.png")
    assert local_url == "http://127.0.0.1:9000/jewelry-media/knowledge/test.png"

    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "")
    monkeypatch.setattr(settings, "S3_REGION", "eu-central-1")
    aws_url = S3Service.object_url("knowledge/test.png")
    assert aws_url == "https://jewelry-media.s3.eu-central-1.amazonaws.com/knowledge/test.png"


def test_object_url_rejects_invalid_key():
    with pytest.raises(HTTPException) as exc:
        S3Service.object_url("../secret.txt")
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid object key"
