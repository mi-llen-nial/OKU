# OKU Prototype

OKU — персонализированная система экзаменов (RU/KZ) с AI-генерацией уникальных тестов, авто-проверкой, рекомендациями по слабым темам и teacher-аналитикой

## Stack
- Backend: FastAPI + SQLAlchemy + JWT
- DB: PostgreSQL
- Frontend: Next.js 14 (responsive)
- AI: `mock` или DeepSeek (`deepseek-chat`)
- STT/TTS: `auto` (бесплатный `edge-tts`) или ElevenLabs

## E2E поток
1. Регистрация/логин (`student` / `teacher`)
2. Выбор предмета, сложности, языка, режима
3. Генерация уникального теста (seed = time + user + subject + difficulty)
4. Прохождение (`text` / `audio` / `oral`)
5. Submit + проверка (`strict` для choice, `fuzzy` для short/oral)
6. Ошибки + объяснения + weak topics + 5 доп. заданий
7. История, прогресс, teacher analytics

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
- `AI_PROVIDER=mock` (или `deepseek` + `DEEPSEEK_API_KEY`)
- `TTS_PROVIDER=auto` (по умолчанию: бесплатный `edge-tts`, без API ключа)
- `TTS_PROVIDER=edge_tts` (принудительно использовать бесплатный серверный TTS)
- `EDGE_TTS_VOICE_RU=ru-RU-SvetlanaNeural` (опционально)
- `EDGE_TTS_VOICE_KZ=kk-KZ-AigulNeural` (опционально)
- `TTS_PROVIDER=elevenlabs` для более реалистичного коммерческого TTS
- `ELEVENLABS_API_KEY=<your_key>`
- `ELEVENLABS_VOICE_ID_RU=<voice_id>` (и опционально `ELEVENLABS_VOICE_ID_KZ=<voice_id>`)

### 4) Установка зависимостей
```bash
cd /Users/mellennial/Programming/KOMA/oku
make setup
```

### 5) Запуск backend
```bash
make backend
```
API будет доступен на `http://localhost:8000`, docs: `http://localhost:8000/docs`.

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

### Frontend
```bash
cd /Users/mellennial/Programming/KOMA/oku
./scripts/build_frontend.sh
./scripts/start_frontend_prod.sh
```

## Sourcecraft deploy (без Docker)
Подробная инструкция: [docs/sourcecraft_deploy.md](docs/sourcecraft_deploy.md)

Коротко:
- Backend service:
  - Workdir: `backend`
  - Build: `pip install -r requirements.txt`
  - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Frontend service:
  - Workdir: `frontend`
  - Build: `npm ci && npm run build`
  - Start: `npm run start`
- `NEXT_PUBLIC_API_URL` должен указывать на URL backend
- На production выстави `SEED_DEMO_DATA=false`

## Demo аккаунты
- Teacher: `teacher@oku.local` / `teacher123`
- Student RU: `student1@oku.local` / `student123`
- Student KZ: `student2@oku.local` / `student123`

## Основные API endpoints
- `POST /auth/register`
- `POST /auth/login`
- `GET /subjects`
- `POST /tests/generate`
- `GET /tests/{id}`
- `POST /tests/{id}/submit`
- `GET /tests/{id}/questions/{question_id}/tts`
- `GET /tests/{id}/result`
- `POST /tests/{id}/recommendations/regenerate`
- `GET /students/me/history`
- `GET /students/me/progress`
- `GET /teacher/groups/{id}/analytics`
- `GET /teacher/groups/{id}/weak-topics`
- `GET /teacher/students/{id}/progress`

## Примеры API запросов

### Login
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"student1@oku.local","password":"student123"}'
```

### Generate test
```bash
curl -X POST http://localhost:8000/tests/generate \
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
curl -X POST http://localhost:8000/tests/5/submit \
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
- Централизованный env (`.env`)
- Разделение ролей student/teacher
- API контракты готовы для web + Flutter
- AI provider abstraction (`mock`/DeepSeek)
- STT/TTS abstraction слой

## Что усилить до полноценного production
- Alembic миграции вместо `create_all`
- Refresh token + rotation
- Rate limit + audit log + retries/queue для AI задач
- Мониторинг/трейсинг (Sentry + metrics)

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
