# Jewelry Onboarding

FastAPI-приложение для адаптации сотрудников, базы знаний и чат-ассистента с опциональным vector-поиском по статьям.

## Локальный запуск

1. Создайте и активируйте виртуальное окружение.
2. Установите зависимости:

```bash
pip install -r backend/requirements.txt
```

3. Создайте `.env.local` в корне проекта на основе `.env.example`.

Минимальный пример:

```env
SECRET_KEY=your-strong-secret
VECTOR_DB_ENABLED=true
VECTOR_SYNC_ON_STARTUP=false
CHAT_USE_LLM=true
LLM_API_URL=https://openrouter.ai/api/v1
LLM_MODEL=qwen/qwen3-next-80b-a3b-instruct:free
LLM_API_KEY=your-openrouter-key
LLM_APP_NAME=Jewelry Onboarding
LLM_HTTP_REFERER=https://your-domain.example
```

## Старт приложения

Из папки `backend`:

```bash
uvicorn app.main:app --reload
```

После старта приложение доступно на `http://localhost:8000`, страница входа на `http://localhost:8000/login`.

## Что важно знать

- SQLite по умолчанию хранится в файле `app.db` в корне проекта.
- Vector DB по умолчанию хранится в папке `vector_db`.
- Все зависимости проекта собраны в одном файле `backend/requirements.txt`.
- Индексация vector-базы больше не запускается автоматически на каждом старте. Это ускоряет запуск и убирает лишнюю нагрузку.
- Если нужна полная пересборка vector-индекса, используйте:

```bash
python backend/scripts/rebuild_knowledge_vector_db.py
```

## Медиа и S3

Если нужны загрузки файлов, заполните S3-переменные в `.env.local`:

```env
S3_BUCKET=
S3_REGION=us-east-1
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_ENDPOINT_URL=
S3_FORCE_PATH_STYLE=false
```

## Быстрая проверка после запуска

1. Откройте `/login`.
2. Создайте первого администратора, если база пустая.
3. Проверьте `/knowledge`.
4. Проверьте `/assistant`.
5. При включённом LLM убедитесь, что переменные OpenRouter заполнены корректно.
