from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.media import PresignDownloadResponse, PresignUploadRequest, PresignUploadResponse
from app.services.s3_service import S3Service

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/presign-upload", response_model=PresignUploadResponse)
def presign_upload(
    payload: PresignUploadRequest,
    _: User = Depends(get_current_user),
):
    return S3Service.create_presigned_upload(
        filename=payload.filename,
        content_type=payload.content_type,
        scope=payload.scope,
    )


@router.get("/presign-download", response_model=PresignDownloadResponse)
def presign_download(
    key: str = Query(min_length=3),
    _: User = Depends(get_current_user),
):
    return S3Service.create_presigned_download(key)
