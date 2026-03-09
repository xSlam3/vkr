import mimetypes
import uuid
from pathlib import Path

from fastapi import HTTPException, status

from app.core.config import settings


class S3Service:
    @staticmethod
    def _get_client():
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="boto3 is not installed",
            ) from exc

        if not settings.S3_BUCKET:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="S3_BUCKET is not configured",
            )

        client_config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.S3_FORCE_PATH_STYLE else "auto"},
        )

        return boto3.client(
            "s3",
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY or None,
            aws_secret_access_key=settings.S3_SECRET_KEY or None,
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            config=client_config,
        )

    @staticmethod
    def _resolve_extension(filename: str, content_type: str) -> str:
        ext = Path(filename).suffix.lower().lstrip(".")
        if ext and ext.isalnum() and len(ext) <= 10:
            return ext

        guessed = mimetypes.guess_extension(content_type) or ""
        guessed = guessed.lstrip(".").lower()
        if guessed and guessed.isalnum():
            return guessed

        return "bin"

    @staticmethod
    def _validate_content_type(content_type: str) -> None:
        if not (content_type.startswith("image/") or content_type.startswith("video/")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only image/* and video/* content types are allowed",
            )

    @staticmethod
    def _validate_key(key: str) -> None:
        if not key or key.startswith("/") or ".." in key or "\\" in key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid object key",
            )

    @staticmethod
    def create_presigned_upload(filename: str, content_type: str, scope: str) -> dict:
        S3Service._validate_content_type(content_type)
        safe_scope = scope.strip().lower()
        if not safe_scope:
            safe_scope = "misc"

        extension = S3Service._resolve_extension(filename, content_type)
        key = f"{safe_scope}/{uuid.uuid4().hex}.{extension}"

        client = S3Service._get_client()
        max_size_bytes = settings.S3_MAX_FILE_SIZE_MB * 1024 * 1024

        post = client.generate_presigned_post(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_size_bytes],
            ],
            ExpiresIn=settings.S3_PRESIGNED_EXPIRES_SECONDS,
        )

        return {
            "key": key,
            "object_url": S3Service.object_url(key),
            "url": post["url"],
            "fields": post["fields"],
            "expires_in": settings.S3_PRESIGNED_EXPIRES_SECONDS,
        }

    @staticmethod
    def create_presigned_download(key: str) -> dict:
        S3Service._validate_key(key)
        client = S3Service._get_client()

        url = client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.S3_BUCKET,
                "Key": key,
            },
            ExpiresIn=settings.S3_PRESIGNED_EXPIRES_SECONDS,
        )
        return {
            "key": key,
            "url": url,
            "expires_in": settings.S3_PRESIGNED_EXPIRES_SECONDS,
        }

    @staticmethod
    def object_url(key: str) -> str:
        S3Service._validate_key(key)
        if settings.S3_ENDPOINT_URL:
            endpoint = settings.S3_ENDPOINT_URL.rstrip("/")
            return f"{endpoint}/{settings.S3_BUCKET}/{key}"
        region = settings.S3_REGION
        return f"https://{settings.S3_BUCKET}.s3.{region}.amazonaws.com/{key}"
