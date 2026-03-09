# Jewelry Onboarding

FastAPI-приложение для адаптации сотрудников, базы знаний и чат-ассистента с векторным поиском по статьям.

## Что входит в деплой

- `docker-compose.yml` поднимает backend-сервис
- `backend/Dockerfile` собирает приложение
- данные SQLite, vector db и кэш моделей сохраняются в docker volume `app_data`

## Что нужно перед запуском

1. Установить Docker и Docker Compose.
2. В корне проекта создать `.env.local`.
3. Заполнить минимум:

```env
SECRET_KEY=your-strong-secret
VECTOR_DB_ENABLED=true
CHAT_USE_LLM=true
LLM_API_URL=https://openrouter.ai/api/v1
LLM_MODEL=qwen/qwen3-next-80b-a3b-instruct:free
LLM_API_KEY=your-openrouter-key
LLM_APP_NAME=Jewelry Onboarding
LLM_HTTP_REFERER=https://your-domain.example
```

Шаблон есть в `.env.example`.

## Запуск

Из корня проекта:

```bash
docker compose up -d --build
```

После старта приложение будет доступно на:

```text
http://localhost:8000
```

Страница логина:

```text
http://localhost:8000/login
```

## Первый запуск

- при первом старте создаются таблицы базы
- если пользователей ещё нет, откроется экран первичной настройки администратора
- при включённом `VECTOR_DB_ENABLED=true` контейнер на старте индексирует статьи в vector db
- embedding-модель может скачиваться несколько минут при первом запуске

## Полезные команды

Пересобрать и поднять сервис:

```bash
docker compose up -d --build
```

Посмотреть логи:

```bash
docker compose logs -f backend
```

Остановить:

```bash
docker compose down
```

Остановить с удалением volume:

```bash
docker compose down -v
```

## Где лежат данные

Внутри контейнера:

- SQLite: `/data/app.db`
- vector db: `/data/vector_db`
- кэш моделей: `/data/huggingface`

Снаружи они сохраняются в docker volume `app_data`.

## S3 / MinIO

Если нужен upload медиа, добавьте S3-переменные в `.env.local`.

Для локального S3/MinIO у проекта уже есть отдельные материалы:

- `backend/LOCAL_S3.md`
- `backend/docker-compose.minio.yml`

## Прод деплой

Для деплоя на сервер обычно достаточно:

1. Скопировать проект на сервер.
2. Создать `.env.local`.
3. Запустить `docker compose up -d --build`.
4. Прокинуть наружу `8000` порт или поставить перед сервисом nginx/caddy.

Если будет reverse proxy, лучше выставить:

```env
LLM_HTTP_REFERER=https://your-domain.example
```

## Проверка после деплоя

1. Открыть `/login`
2. Создать первого администратора
3. Проверить `/knowledge`
4. Проверить `/assistant`
5. Убедиться, что в логах нет ошибок загрузки env и OpenRouter
