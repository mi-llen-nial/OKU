# Sourcecraft Deploy (without Docker)

Проект можно деплоить как 2 отдельных сервиса: `backend` и `frontend`.

## Альтернатива: единый Docker Compose deploy

Если у тебя есть VM/instance в Sourcecraft с установленными Docker и Compose plugin, можно поднимать весь стек одной командой:

```bash
docker compose up -d --build
```

См. детальные шаги и переменные в [project.md](../project.md), раздел «Docker Compose deploy».

## 1) Backend service

- Runtime: Python 3.12+
- Working directory: `backend`
- Build command:
  ```bash
  pip install -r requirements.txt
  ```
- Start command:
  ```bash
  alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```

Required env vars:
- `DATABASE_URL` (Postgres URL)
- `JWT_SECRET_KEY` (32+ chars)
- `JWT_REFRESH_SECRET_KEY` (32+ chars)
- `JWT_ALGORITHM=HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES=720`
- `REFRESH_TOKEN_EXPIRE_DAYS=30`
- `API_PREFIX=/api/v1`
- `ENABLE_LEGACY_ROUTES=true` (временно, для backward compatibility)
- `CORS_ORIGINS=<frontend-url>`
- `REDIS_URL=redis://...`
- `REDIS_ENABLED=true`
- `AI_PROVIDER=mock|deepseek`
- `DEEPSEEK_API_KEY` (если deepseek)
- `DEEPSEEK_BASE_URL=https://api.deepseek.com/v1`
- `DEEPSEEK_MODEL=deepseek-chat`
- `SENTRY_DSN=` (optional)
- `METRICS_ENABLED=true`
- `OTEL_ENABLED=false|true`
- `OTEL_SERVICE_NAME=oku-backend`
- `OTEL_EXPORTER_OTLP_ENDPOINT=<otlp-http-endpoint>` (optional)
- `SEED_DEMO_DATA=false` для production

## 2) Frontend service

- Runtime: Node.js 20+
- Working directory: `frontend`
- Build command:
  ```bash
  npm ci
  npm run build
  ```
- Start command:
  ```bash
  npm run start
  ```

Required env vars:
- `NEXT_PUBLIC_API_URL=<backend-url>`
- `NEXT_PUBLIC_API_PREFIX=/api/v1`

## 3) Postgres

Используй managed Postgres от Sourcecraft и передай его connection string в `DATABASE_URL`.

## 4) Smoke checks after deploy

1. Open `<backend-url>/docs`
2. `POST /api/v1/auth/login` (demo or prod user)
3. `GET /api/v1/subjects`
4. `POST /api/v1/tests/generate`
5. Open frontend and пройти один тест end-to-end
