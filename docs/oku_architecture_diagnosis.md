# OKU Architecture Diagnosis (Grounded)

Этот документ фиксирует текущую реальность архитектуры OKU на основе кода и деплойных артефактов в репозитории. Цель: заранее обозначить узкие места, которые начнут болеть при росте ролей/нагрузки/AI-функций и при появлении “контента” в виде бинарников (docx/pptx/images).

## 1) Архитектурный стиль: модульный монолит

Backend написан на FastAPI и организован как модульный монолит: доменная логика разнесена по `app/services/*` и `app/core/*`, а роуты — по `app/api/*`.

Примеры “хороших границ”:
- RBAC/институциональный доступ сосредоточен в `backend/app/core/deps.py`.
- Кэш/Ratelimit — в `backend/app/services/cache.py` и `backend/app/core/rate_limit.py`.
- LLM/AI-обвязка — в `backend/app/services/llm/*` + доменные сервисы (`evaluation.py`, `teacher_material_service.py` и др.).

## 2) Auth / sessions / JWT

Авторизация построена на JWT access/refresh + server-side `UserSession`.

Ключевой механизм валидируется в:
- `backend/app/core/deps.py` (`get_current_user`):
  - достает `sid` из JWT,
  - грузит `UserSession` из Postgres,
  - проверяет `revoked_at is None`,
  - обновляет `UserSession.last_used_at` не чаще 1 раза в ~60 сек.

Что это значит для роста:
- При горизонтальном масштабе и росте RPS будет ощутима нагрузка на Postgres из-за обращения за сессией “на каждый запрос”.
- Heartbeat (commit раз в ~60 сек) снижает write-amplification, но “read per request” все равно останется.

Модели:
- `backend/app/models/entities.py`: `UserSession` хранит `refresh_token_hash`, `user_agent`, `ip_address`, `expires_at`, `revoked_at`.

## 3) Roles / институциональный RBAC

Институциональный доступ реализован через `InstitutionMembership` и membership roles.

Главные компоненты:
- `backend/app/core/deps.py`:
  - `get_active_memberships()`
  - `get_active_membership_or_403()`
  - `require_institution_role()`
- `backend/app/models/entities.py`:
  - `InstitutionMembership`, `InstitutionMembershipRole`, `InstitutionMembershipStatus`.

Переходная логика:
- В `backend/app/core/deps.py` есть special handling для `superadmin` (выбор членства без обязательного `institution_id`).
- В `backend/app/api/tests.py` есть “legacy fallback” для групп без RBAC-институции (`Group.institution_id is None`).

Что может болеть:
- Рост числа ролей/институций увеличит количество join/where в типовых запросах.
- Наличие legacy-пути увеличивает сложность поддержания invariants (“какие правила истинны”).

## 4) Teacher flows: генерация материалов и импорт файлов

### 4.1. Импорт docx/csv

Роут принимает `UploadFile` и читает весь файл в память:
- `backend/app/api/teacher.py`:
  - `POST /teacher/custom-tests/parse-file`
  - лимит размера: `MAX_IMPORT_SIZE_BYTES` (см. `backend/app/services/teacher_file_import.py`)

Парсинг реализован как:
- `backend/app/services/teacher_file_import.py`:
  - `.docx`: извлекает `word/document.xml`, сопоставляет embedded images и конструирует `image_data_url` как `data:image/*;base64,...`
  - `.csv`: собирает поля, включая `image_data_url` (возможный `data:image/...`).

Почему это важно:
- Сейчас бинарные изображения попадают в API/JSON и затем в БД как база64.
- Это создаёт “скрытый рост” объема Postgres (JSON/large-text) и увеличивает размер payload по API.

### 4.2. Хранение изображений в БД через `image_data_url`

При создании/обновлении teacher custom test:
- `backend/app/api/teacher.py`:
  - `_replace_custom_test_questions()`
  - если есть `image_data_url`, то кладется в `TeacherAuthoredQuestion.options_json["image_data_url"]`.

Schema:
- `backend/app/models/entities.py`: `TeacherAuthoredQuestion.options_json` — `JSON`.

Ограничение на размер изображения:
- `backend/app/schemas/teacher_tests.py` валидирует `image_data_url` (max_len = 10_000_000) и проверяет base64 + размер (ограничение `MAX_QUESTION_IMAGE_BYTES = 1MB` в `teacher_tests.py`).

## 5) AI-heavy операции: синхронность в HTTP

### 5.1. Teacher material generation синхронно

HTTP-запрос вызывает LLM генерацию напрямую:
- `backend/app/api/teacher.py` → `teacher_material_service.generate_and_validate()`

LLM pipeline:
- `backend/app/services/teacher_material_service.py`
  - делает up to `max_calls` попыток генерации,
  - валидирует батчи (`validate_question_payload`, собственная нормализация),
  - возвращает список `TeacherCustomMaterialQuestion`.

Компромисс:
- Это проще по архитектуре, но при росте это становится главным источником “долгих запросов” и вариативности latency.

### 5.2. Student semantic evaluation также AI-ветвление

В `backend/app/services/evaluation.py` есть semantic grading:
- включается не всегда, но может инициировать LLM вызов для free-text ответов.

## 6) Background jobs: RQ/worker и миграции

RQ используется минимально, через `backend/app/worker/queue.py`:
- `enqueue_task()` кладет задачи в queue Redis.
- `get_job_status()` позволяет polling по `job_id`.

Worker стартует так:
- `docker-compose.yml`:
  - `worker.command: ["sh", "-c", "alembic upgrade head && rq worker default"]`

Что это значит для горизонтального масштабирования:
- При запуске нескольких worker replicas есть риск конкуренции из-за одновременного `alembic upgrade head`.
- Это “размазывает” ответственность: инфраструктурные операции (миграции) происходят внутри runtime worker.

## 7) Observability / rate limiting / infra health

Наблюдаемость:
- `backend/app/main.py`:
  - JSON structured logging (`backend/app/core/logging_config.py`)
  - `/metrics` через `prometheus-fastapi-instrumentator`
  - optional tracing через OpenTelemetry.

Rate limit:
- `backend/app/core/rate_limit.py` использует Redis bucket counter.
- Docs/health endpoints исключаются по whitelist.

## 8) Deploy реальность vs репозиторий

В репозитории есть production-ориентированный контейнерный сценарий (`docker-compose.yml`, `deploy/Caddyfile`).

Но по текущему процессу эксплуатации (описано в задаче пользователя):
- frontend в проде — Vercel,
- backend — Render,
- есть дублирование контента/логики между репозиториями и отдельные push.

Узкое место:
- это ухудшает предсказуемость релизов и увеличивает вероятность “несовпадения” версий фронта/бэка.

