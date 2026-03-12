# OKU Prototype

OKU — персонализированная система экзаменов (RU/KZ) с AI-генерацией уникальных тестов, авто-проверкой, рекомендациями по слабым темам и teacher-аналитикой.


## Stack
- Backend: FastAPI + SQLAlchemy + Alembic + JWT (access/refresh)
- DB: PostgreSQL
- Cache/Queue: Redis + RQ worker
- Frontend: Next.js 14 (responsive)
- AI: раздельно по ролям
  - student: `gemini`
  - teacher: `claude`
- STT/TTS: `auto` (бесплатный `edge-tts`) или ElevenLabs
- Observability: JSON logs + Prometheus `/metrics` + optional Sentry
- Deploy: Docker Compose + Caddy (HTTPS, Let's Encrypt)

## E2E поток
1. Регистрация/логин (`student` / `teacher`)
2. Выбор предмета, сложности, языка, режима
3. Генерация уникального теста (seed = time + user + subject + difficulty)
4. Прохождение (`text` / `audio` / `oral`)
5. Submit + проверка (`strict` для choice, `fuzzy` для short/oral)
6. Ошибки + объяснения + weak topics + 5 доп. заданий
7. История, прогресс, teacher analytics

## Docker Compose deploy (frontend + backend + db + domain)

В репозитории есть готовый `docker-compose.yml`:
- `db` (PostgreSQL 16)
- `redis` (cache + queue)
- `backend` (FastAPI)
- `worker` (RQ)
- `frontend` (Next.js production build)
- `proxy` (Caddy с авто HTTPS)

### 1) DNS для домена `oku.com.kz`
У регистратора домена добавь A-записи на IP сервера:
- `oku.com.kz` -> `<SERVER_IP>`
- `www.oku.com.kz` -> `<SERVER_IP>`
- `api.oku.com.kz` -> `<SERVER_IP>`

Открой на сервере порты `80` и `443`.

### 2) Обнови `.env` под production
Минимально проверь/добавь:

```dotenv
# Domain
APP_DOMAIN=oku.com.kz
API_DOMAIN=api.oku.com.kz
LETSENCRYPT_EMAIL=admin@oku.com.kz
PUBLIC_API_URL=https://api.oku.com.kz
PUBLIC_API_PREFIX=/api/v1
BACKEND_CORS_ORIGINS=https://oku.com.kz,https://www.oku.com.kz

# Security
JWT_SECRET_KEY=<strong-random-secret-32+>
JWT_REFRESH_SECRET_KEY=<strong-random-refresh-secret-32+>
API_PREFIX=/api/v1
ENABLE_LEGACY_ROUTES=true

# Database (внутри compose подставится автоматически)
POSTGRES_DB=oku
POSTGRES_USER=oku
POSTGRES_PASSWORD=<strong-db-password>

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_ENABLED=true

# Observability (optional)
SENTRY_DSN=
METRICS_ENABLED=true
OTEL_ENABLED=false
OTEL_SERVICE_NAME=oku-backend
OTEL_EXPORTER_OTLP_ENDPOINT=

# AI (role-based)
STUDENT_AI_PROVIDER=gemini
TEACHER_AI_PROVIDER=claude
GEMINI_API_KEY=<your-gemini-key>
CLAUDE_API_KEY=<your-claude-key>
# optional fallback/global (не обязателен при role-based настройке)
AI_PROVIDER=mock

# Recommended for prod
PROD_SEED_DEMO_DATA=false
```

`DATABASE_URL` вручную для Docker указывать не нужно: compose подставляет контейнер БД автоматически.

### 3) Запуск
```bash
docker compose up -d --build
```

Проверка:
- `https://oku.com.kz`
- `https://api.oku.com.kz/docs`

Полезные команды:
```bash
docker compose logs -f --tail=150
docker compose ps
docker compose down
```

### 4) Если сертификат не выдан
- Проверь, что DNS уже резолвится в IP сервера.
- Убедись, что 80/443 доступны извне.
- Проверь логи прокси:
```bash
docker compose logs proxy
```

## Локальный запуск без Docker

### 1) Требования
- Python 3.11+
- Node.js 20+
- PostgreSQL 15+

### 2) Поднять локальный Postgres
Создай БД и пользователя (пример):

```sql
CREATE USER oku WITH PASSWORD 'oku';
CREATE DATABASE oku OWNER oku;
GRANT ALL PRIVILEGES ON DATABASE oku TO oku;
```

### 3) Проверить `.env`
В проекте уже есть рабочий `.env` для локального запуска.

Ключевые поля:
- `DATABASE_URL=postgresql+psycopg://oku:oku@localhost:5432/oku`
- `NEXT_PUBLIC_API_URL=http://localhost:8000`
- `STUDENT_AI_PROVIDER=gemini`
- `TEACHER_AI_PROVIDER=claude`
- `GEMINI_API_KEY=<your_gemini_key>`
- `CLAUDE_API_KEY=<your_claude_key>`
- `AI_PROVIDER=mock` (опциональный общий fallback; для role-based можно оставить как есть)
- `TTS_PROVIDER=auto` (по умолчанию: бесплатный `edge-tts`, без API ключа)
- `TTS_PROVIDER=edge_tts` (принудительно использовать бесплатный серверный TTS)
- `EDGE_TTS_VOICE_RU=ru-RU-SvetlanaNeural` (опционально)
- `EDGE_TTS_VOICE_KZ=kk-KZ-AigulNeural` (опционально)
- `TTS_PROVIDER=elevenlabs` для более реалистичного коммерческого TTS
- `ELEVENLABS_API_KEY=<your_key>`
- `ELEVENLABS_VOICE_ID_RU=<voice_id>` (и опционально `ELEVENLABS_VOICE_ID_KZ=<voice_id>`)
- `EMAIL_VERIFICATION_ENABLED=true`
- `EMAIL_PROVIDER=smtp` (локально) или `EMAIL_PROVIDER=sendgrid|resend` (prod)
- `SMTP_HOST=smtp.office365.com` (если `EMAIL_PROVIDER=smtp`)
- `SMTP_PORT=587`
- `SMTP_STARTTLS=true`
- `SMTP_USERNAME=<корпоративная_почта>`
- `SMTP_PASSWORD=<пароль_почты>`
- `SMTP_FROM_EMAIL=<корпоративная_почта>` (или верифицированный sender в SendGrid)
- `SMTP_FROM_NAME=OKU`
- `SENDGRID_API_KEY=<sendgrid_api_key>` (если `EMAIL_PROVIDER=sendgrid`)
- `SENDGRID_BASE_URL=https://api.sendgrid.com/v3`
- `EMAIL_PROVIDER=resend` (рекомендуется для production)
- `RESEND_API_KEY=<resend_api_key>`
- `RESEND_BASE_URL=https://api.resend.com`
- `SMTP_FROM_EMAIL=<верифицированный_sender_email>`

### Импорт теста из файла (сторона преподавателя)
- На странице `Создать тест` доступен режим `Создать из файла`.
- Поддерживаемые форматы: `.docx`, `.csv`.
- Лимит размера файла: `5MB`.
- Для `.docx` используется шаблон с тегами:
  - `<q>` — текст вопроса
  - `<a>` — неверный вариант
  - `<+a>` — правильный вариант
- Пример:
  - `<q>Когда празднуют День Независимости Казахстана?`
  - `<+a>16 декабря<a>17 декабря`
  - `<a>1 декабря<a>31 декабря`

### 4) Установка зависимостей
```bash
cd /Users/mellennial/Programming/KOMA/oku
make setup
```

### 5) Запуск backend
```bash
make backend
```
Скрипт автоматически применяет миграции Alembic (`alembic upgrade head`) и запускает API.  
API доступен на:
- versioned: `http://localhost:8000/api/v1`
- legacy: `http://localhost:8000` (временно для обратной совместимости)
- docs: `http://localhost:8000/docs`

### 6) Запуск frontend
В отдельном терминале:
```bash
cd /Users/mellennial/Programming/KOMA/oku
make frontend
```
Frontend: `http://localhost:3000`.

### Troubleshooting Postgres
Если при `make backend` видишь ошибку `role "oku" does not exist`, выполни:
```bash
psql -d postgres -c "CREATE ROLE oku WITH LOGIN PASSWORD 'oku';"
psql -d postgres -c "CREATE DATABASE oku OWNER oku;"
```
Проверка:
```bash
psql "postgresql://oku:oku@localhost:5432/oku" -c "SELECT current_user, current_database();"
```

## Build/Start (production-like, без Docker)

### Backend
```bash
cd /Users/mellennial/Programming/KOMA/oku
./scripts/start_backend_prod.sh
```
Скрипт применяет миграции перед запуском.

### Frontend
```bash
cd /Users/mellennial/Programming/KOMA/oku
./scripts/build_frontend.sh
./scripts/start_frontend_prod.sh
```

## Sourcecraft deploy (без Docker)
Подробная инструкция: [docs/sourcecraft_deploy.md](docs/sourcecraft_deploy.md)

## Engineering workflow
Рекомендованный прод-процесс: [docs/engineering_workflow.md](docs/engineering_workflow.md)

Коротко:
- Backend service:
  - Workdir: `backend`
  - Build: `pip install -r requirements.txt`
  - Start: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Frontend service:
  - Workdir: `frontend`
  - Build: `npm ci && npm run build`
  - Start: `npm run start`
- `NEXT_PUBLIC_API_URL` должен указывать на URL backend
- `NEXT_PUBLIC_API_PREFIX=/api/v1`
- На production выстави `SEED_DEMO_DATA=false`

## Demo аккаунты
- Teacher: `teacher@oku.local` / `teacher123`
- Student RU: `student1@oku.local` / `student123`
- Student KZ: `student2@oku.local` / `student123`

## Основные API endpoints
- Базовый префикс: `/api/v1`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/register/send-code`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/subjects`
- `POST /api/v1/tests/generate`
- `GET /api/v1/tests/{id}`
- `POST /api/v1/tests/{id}/submit`
- `GET /api/v1/tests/{id}/questions/{question_id}/tts`
- `GET /api/v1/tests/{id}/result`
- `POST /api/v1/tests/{id}/recommendations/regenerate`
- `GET /api/v1/students/me/history`
- `GET /api/v1/students/me/progress`
- `GET /api/v1/students/me/dashboard` (объединенный endpoint для быстрой загрузки главной)
- `GET /api/v1/teacher/groups/{id}/analytics`
- `GET /api/v1/teacher/groups/{id}/weak-topics`
- `GET /api/v1/teacher/students/{id}/progress`
- `POST /api/v1/jobs/ping` + `GET /api/v1/jobs/{job_id}` (worker health/check)

## Примеры API запросов

### Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"student1@oku.local","password":"student123","remember_me":true}'
```

### Регистрация с кодом почты
```bash
curl -X POST http://localhost:8000/api/v1/auth/register/send-code \
  -H "Content-Type: application/json" \
  -d '{"email":"new.user@example.com"}'

curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email":"new.user@example.com",
    "full_name":"Новый Пользователь",
    "username":"new_user_1",
    "password":"StrongPass123",
    "role":"student",
    "preferred_language":"RU",
    "education_level":"school",
    "direction":"Общий профиль",
    "email_verification_code":"123456"
  }'
```

### Generate test
```bash
curl -X POST http://localhost:8000/api/v1/tests/generate \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id":1,
    "difficulty":"medium",
    "language":"RU",
    "mode":"audio",
    "num_questions":10
  }'
```

### Submit test
```bash
curl -X POST http://localhost:8000/api/v1/tests/5/submit \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "answers": [
      {"question_id":11, "student_answer_json":{"selected_option_ids":[1]}},
      {"question_id":12, "student_answer_json":{"text":"мой ответ"}},
      {"question_id":13, "student_answer_json":{"spoken_answer_text":"устный ответ"}}
    ]
  }'
```

## Что уже прод-ориентировано
- Alembic миграции вместо runtime `create_all/ALTER`
- Versioned API `/api/v1` + временная backward совместимость
- JWT access/refresh + server-side `user_sessions`
- Redis cache (subjects/progress/history) + базовый rate limiting middleware
- Локальный кэш на frontend (localStorage TTL) для ускорения загрузки после входа
- Базовая observability: JSON logs, `/metrics`, optional Sentry
- Контракт-first поток: экспорт OpenAPI + скрипты генерации SDK

## Что усилить до полноценного production
- Перевести heavy AI операции (`generate/evaluate/recommend/TTS`) полностью в async queue pipeline
- Добавить интеграционные/нагрузочные тесты и CI quality gates
- Включить полноценный OpenTelemetry tracing
- Добавить feature flags и staging rollout policy
- Формализовать data governance (PII policy, retention, backup/restore drills)

## Контракт-first команды
```bash
make openapi          # экспорт contracts/openapi.json
make sdk              # генерация TS + Dart SDK (requires Docker for Dart generator)
```

## Flutter клиент
См. [docs/flutter_client.md](docs/flutter_client.md).

### Быстрый запуск mobile
```bash
cd mobile
flutter pub get
flutter run
```

### Сборка iOS (debug, без codesign)
```bash
cd mobile
flutter build ios --debug --no-codesign
```

Открыть в Xcode:
```bash
open mobile/ios/Runner.xcworkspace
```

## UI Assets и палитра
- Ассеты web UI: `frontend/public/assets/*`
- Реестр ассетов: `frontend/src/assets/index.ts`
- Theme tokens: `frontend/src/theme/tokens.ts`
- Сгенерированная бренд-палитра: `frontend/src/theme/brand.generated.ts`

### Как заменить лого и обновить бренд-цвета
1. Замените файл `frontend/public/assets/logo/logo.png`
2. Выполните:
   ```bash
   cd frontend
   npm run extract-palette
   ```
3. Проверьте изменения в `src/theme/brand.generated.ts`

### Как добавлять иконки/изображения
1. Добавьте файл в `frontend/public/assets/icons` или `frontend/public/assets/images`
2. Зарегистрируйте путь в `frontend/src/assets/index.ts`
3. Используйте путь из реестра в компонентах/страницах
