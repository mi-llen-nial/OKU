from functools import lru_cache

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
    api_prefix: str = ""

    database_url: str = "postgresql+psycopg://oku:oku@localhost:5432/oku"

    jwt_secret_key: str = "change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    cors_origins: str = "http://localhost:3000"

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

    seed_demo_data: bool = True
    teacher_max_groups: int = 3
    group_max_members: int = 5

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
