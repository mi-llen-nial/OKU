import os
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "OKU Prototype"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    enable_legacy_routes: bool = False

    database_url: str = "postgresql+psycopg://oku:oku@localhost:5432/oku"
    db_pool_size: int = 20
    db_max_overflow: int = 40
    db_pool_timeout_seconds: int = 30

    jwt_secret_key: str = "dev-insecure-secret-change-before-production-oku-2026"
    jwt_refresh_secret_key: str = "dev-insecure-refresh-secret-change-before-production-oku-2026"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12
    refresh_token_expire_days: int = 30
    use_http_only_refresh_cookie: bool = False
    refresh_cookie_name: str = "oku_refresh_token"
    admin_key: str = ""

    # Comma-separated allowed browser origins. Two env names are supported for backwards
    # compatibility; see `cors_origins_list` which merges both if both are set.
    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("CORS_ORIGINS", "BACKEND_CORS_ORIGINS"),
    )

    ai_provider: str = "openai"
    student_ai_provider: str = "openai"
    teacher_ai_provider: str = "openai"
    openai_api_key: str = ""
    openai_api_key_student: str = ""
    openai_api_key_teacher: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5"
    openai_model_fallbacks: str = "gpt-4.1-mini,gpt-4o-mini"
    openai_timeout_seconds: int = 45
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    gemini_api_key: str = ""
    gemini_api_key_one: str = ""
    gemini_api_key_two: str = ""
    gemini_api_key_student: str = ""
    gemini_api_key_teacher: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-2.5-flash"
    claude_api_key: str = ""
    claude_base_url: str = "https://api.anthropic.com/v1"
    claude_model: str = "claude-sonnet-4-5"
    claude_max_tokens: int = 1024
    semantic_grading_max_ai_calls_per_test: int = 3

    tts_provider: str = "auto"
    tts_voice: str = "default"
    edge_tts_voice_ru: str = "ru-RU-SvetlanaNeural"
    edge_tts_voice_kz: str = "kk-KZ-AigulNeural"
    edge_tts_rate: str = "+0%"
    edge_tts_pitch: str = "+0Hz"
    edge_tts_volume: str = "+0%"
    tts_timeout_seconds: int = 20
    elevenlabs_api_key: str = ""
    elevenlabs_base_url: str = "https://api.elevenlabs.io/v1"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_output_format: str = "mp3_44100_128"
    elevenlabs_voice_id_ru: str = ""
    elevenlabs_voice_id_kz: str = ""
    elevenlabs_stability: float = 0.42
    elevenlabs_similarity_boost: float = 0.82
    elevenlabs_style: float = 0.22
    elevenlabs_speaker_boost: bool = True

    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    cache_subjects_ttl_seconds: int = 3600
    cache_progress_ttl_seconds: int = 30
    cache_history_ttl_seconds: int = 30
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 180

    # Where teacher question images/materials are stored.
    # "db" keeps inline `image_data_url` in Postgres JSON (current behavior).
    # "object" is prepared for future S3-compatible migration (ref fields only for now).
    material_storage_mode: str = "db"

    sentry_dsn: str = ""
    metrics_enabled: bool = True
    otel_enabled: bool = False
    otel_service_name: str = "oku-backend"
    otel_exporter_otlp_endpoint: str = ""

    seed_demo_data: bool = True
    teacher_max_groups: int = 3
    group_max_members: int = 30
    catalog_auto_import_csv_on_startup: bool = True
    catalog_auto_import_csv_path: str = "app/db/database_question.csv"
    catalog_auto_import_csv_source: str = "csv_question_bank"
    catalog_auto_import_csv_publish: bool = True
    catalog_auto_import_csv_replace_existing: bool = True
    catalog_auto_import_csv_fail_fast: bool = False

    email_verification_enabled: bool = True
    email_verification_code_ttl_minutes: int = 10
    email_verification_resend_cooldown_seconds: int = 60
    email_provider: str = "smtp"
    smtp_host: str = "smtp.office365.com"
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "OKU"
    sendgrid_api_key: str = ""
    sendgrid_base_url: str = "https://api.sendgrid.com/v3"
    sendgrid_timeout_seconds: int = 20
    resend_api_key: str = ""
    resend_base_url: str = "https://api.resend.com"
    resend_timeout_seconds: int = 20

    # Password reset (Resend email + one-time token)
    password_reset_token_ttl_minutes: int = 30
    password_reset_request_resend_cooldown_seconds: int = 60
    frontend_app_url: str = Field(default="", validation_alias=AliasChoices("NEXT_PUBLIC_APP_URL", "FRONTEND_APP_URL"))

    @property
    def cors_origins_list(self) -> list[str]:
        """
        Merge `CORS_ORIGINS` and `BACKEND_CORS_ORIGINS` from the environment when both are set.
        Pydantic only keeps one value in `cors_origins`, so reading both keys avoids losing origins
        (e.g. localhost from one line and app.oku.com.kz from another).
        """
        merged_chunks: list[str] = []
        for key in ("CORS_ORIGINS", "BACKEND_CORS_ORIGINS"):
            raw = (os.environ.get(key) or "").strip()
            if raw:
                merged_chunks.append(raw)

        combined = ",".join(merged_chunks) if merged_chunks else (self.cors_origins or "")

        origins: list[str] = []
        for raw_origin in combined.split(","):
            normalized = raw_origin.strip().rstrip("/")
            if normalized:
                origins.append(normalized)

        # In local/dev mode, always allow common local frontend origins.
        if self.app_env.lower() != "production":
            origins.extend(
                [
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                ]
            )

        unique_origins: list[str] = []
        for origin in origins:
            if origin not in unique_origins:
                unique_origins.append(origin)
        return unique_origins

    @property
    def api_prefix_normalized(self) -> str:
        prefix = self.api_prefix.strip()
        if not prefix:
            prefix = "/api/v1"
        return prefix if prefix.startswith("/") else f"/{prefix}"

    @property
    def jwt_refresh_secret(self) -> str:
        return self.jwt_refresh_secret_key.strip() or self.jwt_secret_key.strip()

    def get_openai_api_key(self, audience: str | None = None) -> str:
        normalized_audience = str(audience or "").strip().lower()
        if normalized_audience == "teacher":
            return (
                self.openai_api_key_teacher.strip()
                or self.openai_api_key.strip()
                or self.openai_api_key_student.strip()
            )
        if normalized_audience == "student":
            return (
                self.openai_api_key_student.strip()
                or self.openai_api_key.strip()
                or self.openai_api_key_teacher.strip()
            )
        return (
            self.openai_api_key.strip()
            or self.openai_api_key_teacher.strip()
            or self.openai_api_key_student.strip()
        )

    def get_openai_api_keys(self, audience: str | None = None) -> list[str]:
        normalized_audience = str(audience or "").strip().lower()
        if normalized_audience == "teacher":
            ordered = [
                self.openai_api_key_teacher.strip(),
                self.openai_api_key.strip(),
                self.openai_api_key_student.strip(),
            ]
        elif normalized_audience == "student":
            ordered = [
                self.openai_api_key_student.strip(),
                self.openai_api_key.strip(),
                self.openai_api_key_teacher.strip(),
            ]
        else:
            ordered = [
                self.openai_api_key.strip(),
                self.openai_api_key_teacher.strip(),
                self.openai_api_key_student.strip(),
            ]

        unique: list[str] = []
        for key in ordered:
            if key and key not in unique:
                unique.append(key)
        return unique

    def get_openai_model_candidates(self) -> list[str]:
        primary = (self.openai_model or "").strip() or "gpt-5"
        raw_fallbacks = [
            item.strip()
            for item in str(self.openai_model_fallbacks or "").split(",")
            if item.strip()
        ]
        # Safety fallback: even if OPENAI_MODEL_FALLBACKS is empty in env,
        # keep a couple of broadly available models so generation can continue.
        safety_fallbacks = ["gpt-4.1-mini", "gpt-4o-mini"]
        ordered = [primary, *raw_fallbacks, *safety_fallbacks]
        unique: list[str] = []
        for model in ordered:
            if model not in unique:
                unique.append(model)
        return unique

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value):  # type: ignore[no-untyped-def]
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return bool(value)

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
