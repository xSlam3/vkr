# Local S3 (MinIO)

## 1) Start local S3
```powershell
docker compose -f docker-compose.minio.yml up -d
```

MinIO endpoints:
- S3 API: `http://127.0.0.1:9000`
- Console: `http://127.0.0.1:9001`
- Login: `minioadmin / minioadmin`

## 2) Configure backend env
Use values from `.env.local.s3.example`.

PowerShell example:
```powershell
$env:S3_BUCKET="jewelry-media"
$env:S3_REGION="us-east-1"
$env:S3_ACCESS_KEY="minioadmin"
$env:S3_SECRET_KEY="minioadmin"
$env:S3_ENDPOINT_URL="http://127.0.0.1:9000"
$env:S3_FORCE_PATH_STYLE="true"
$env:S3_PRESIGNED_EXPIRES_SECONDS="300"
$env:S3_MAX_FILE_SIZE_MB="50"
```

## 3) Create bucket and CORS with Python
```powershell
.\venv\Scripts\python scripts\setup_local_s3.py
```

## 4) Run backend
```powershell
.\venv\Scripts\python -m uvicorn app.main:app --reload
```

## 5) Test media endpoints
1. Login and get JWT: `POST /users/login`
2. Request upload URL: `POST /media/presign-upload`
3. Upload file directly to MinIO by returned `url + fields`
4. Request download URL: `GET /media/presign-download?key=...`
