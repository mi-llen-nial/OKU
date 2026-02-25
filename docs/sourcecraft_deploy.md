# Sourcecraft Deploy (without Docker)

Проект можно деплоить как 2 отдельных сервиса: `backend` и `frontend`.

## 1) Backend service

- Runtime: Python 3.12+
- Working directory: `backend`
- Build command:
  ```bash
  pip install -r requirements.txt
  ```
- Start command:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```

Required env vars:
- `DATABASE_URL` (Postgres URL)
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM=HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES=720`
- `CORS_ORIGINS=<frontend-url>`
- `AI_PROVIDER=mock|deepseek`
- `DEEPSEEK_API_KEY` (если deepseek)
- `DEEPSEEK_BASE_URL=https://api.deepseek.com/v1`
- `DEEPSEEK_MODEL=deepseek-chat`
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

## 3) Postgres

Используй managed Postgres от Sourcecraft и передай его connection string в `DATABASE_URL`.

## 4) Smoke checks after deploy

1. Open `<backend-url>/docs`
2. `POST /auth/login` (demo or prod user)
3. `GET /subjects`
4. `POST /tests/generate`
5. Open frontend and пройти один тест end-to-end
