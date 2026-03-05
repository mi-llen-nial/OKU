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
    enable_legacy_routes: bool = True

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

    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("CORS_ORIGINS", "BACKEND_CORS_ORIGINS"),
    )

    ai_provider: str = "mock"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

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

    sentry_dsn: str = ""
    metrics_enabled: bool = True
    otel_enabled: bool = False
    otel_service_name: str = "oku-backend"
    otel_exporter_otlp_endpoint: str = ""

    seed_demo_data: bool = True
    teacher_max_groups: int = 3
    group_max_members: int = 5

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

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def api_prefix_normalized(self) -> str:
        prefix = self.api_prefix.strip()
        if not prefix:
            prefix = "/api/v1"
        return prefix if prefix.startswith("/") else f"/{prefix}"

    @property
    def jwt_refresh_secret(self) -> str:
        return self.jwt_refresh_secret_key.strip() or self.jwt_secret_key.strip()

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
