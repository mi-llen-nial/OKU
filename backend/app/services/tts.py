from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from typing import Protocol

import httpx

from app.core.config import settings
from app.models import PreferredLanguage


class TTSServiceError(RuntimeError):
    pass


class TTSProviderUnavailableError(TTSServiceError):
    pass


@dataclass
class TTSResponse:
    tts_text: str
    audio_bytes: bytes
    content_type: str = "audio/mpeg"


class TTSProvider(Protocol):
    def synthesize(self, text: str, *, language: PreferredLanguage, voice: str = "default") -> TTSResponse:
        ...


class MockTTSProvider:
    def synthesize(self, text: str, *, language: PreferredLanguage, voice: str = "default") -> TTSResponse:
        raise TTSProviderUnavailableError(
            "Серверный TTS не настроен. Используйте TTS_PROVIDER=auto/edge_tts либо настройте ElevenLabs."
        )


class EdgeTTSProvider:
    def __init__(self) -> None:
        self._cache: dict[str, TTSResponse] = {}
        self._cache_order: list[str] = []
        self._cache_limit = 256

    def synthesize(self, text: str, *, language: PreferredLanguage, voice: str = "default") -> TTSResponse:
        edge_tts = _load_edge_tts_module()
        if edge_tts is None:
            raise TTSProviderUnavailableError(
                "Пакет edge-tts не установлен. Выполните: pip install -r backend/requirements.txt"
            )

        prepared_text = prepare_tts_text(text)
        if not prepared_text:
            raise TTSServiceError("Пустой текст для озвучки.")

        voice_name = self._resolve_voice_name(language=language, voice=voice)
        cache_key = self._cache_key(
            voice_name=voice_name,
            rate=settings.edge_tts_rate,
            pitch=settings.edge_tts_pitch,
            volume=settings.edge_tts_volume,
            text=prepared_text,
        )
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        try:
            audio_bytes = _run_async(
                self._synthesize_async(
                    edge_tts=edge_tts,
                    text=prepared_text,
                    voice_name=voice_name,
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise TTSServiceError(f"Ошибка Edge TTS: {exc}") from exc

        if not audio_bytes:
            raise TTSServiceError("Edge TTS вернул пустой аудио-ответ.")

        result = TTSResponse(tts_text=prepared_text, audio_bytes=audio_bytes, content_type="audio/mpeg")
        self._remember(cache_key, result)
        return result

    async def _synthesize_async(self, *, edge_tts: Any, text: str, voice_name: str) -> bytes:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_name,
            rate=settings.edge_tts_rate,
            pitch=settings.edge_tts_pitch,
            volume=settings.edge_tts_volume,
        )
        chunks: list[bytes] = []
        async for part in communicate.stream():
            if not isinstance(part, dict):
                continue
            if part.get("type") != "audio":
                continue
            payload = part.get("data")
            if isinstance(payload, (bytes, bytearray)):
                chunks.append(bytes(payload))
        return b"".join(chunks)

    @staticmethod
    def _resolve_voice_name(*, language: PreferredLanguage, voice: str) -> str:
        normalized_voice = voice.strip()
        if normalized_voice and normalized_voice != "default":
            return normalized_voice
        if language == PreferredLanguage.kz:
            return settings.edge_tts_voice_kz.strip() or settings.edge_tts_voice_ru.strip()
        return settings.edge_tts_voice_ru.strip() or "ru-RU-SvetlanaNeural"

    @staticmethod
    def _cache_key(*, voice_name: str, rate: str, pitch: str, volume: str, text: str) -> str:
        digest = hashlib.sha256(f"{voice_name}|{rate}|{pitch}|{volume}|{text}".encode("utf-8")).hexdigest()
        return digest

    def _remember(self, key: str, value: TTSResponse) -> None:
        if key in self._cache:
            return
        self._cache[key] = value
        self._cache_order.append(key)
        while len(self._cache_order) > self._cache_limit:
            old = self._cache_order.pop(0)
            self._cache.pop(old, None)


class ElevenLabsTTSProvider:
    def __init__(self) -> None:
        self._cache: dict[str, TTSResponse] = {}
        self._cache_order: list[str] = []
        self._cache_limit = 256
        self._autodetected_voice_ids: dict[str, str] = {}

    def synthesize(self, text: str, *, language: PreferredLanguage, voice: str = "default") -> TTSResponse:
        if not settings.elevenlabs_api_key:
            raise TTSProviderUnavailableError("Отсутствует ELEVENLABS_API_KEY.")

        voice_id = self._resolve_voice_id(language=language, voice=voice)
        if not voice_id:
            raise TTSProviderUnavailableError(
                "Не найден voice_id для выбранного языка. Укажите ELEVENLABS_VOICE_ID_RU/KZ."
            )

        prepared_text = prepare_tts_text(text)
        if not prepared_text:
            raise TTSServiceError("Пустой текст для озвучки.")

        cache_key = self._cache_key(
            voice_id=voice_id,
            model_id=settings.elevenlabs_model_id,
            output_format=settings.elevenlabs_output_format,
            text=prepared_text,
        )
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        url = f"{settings.elevenlabs_base_url.rstrip('/')}/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }
        payload = {
            "text": prepared_text,
            "model_id": settings.elevenlabs_model_id,
            "output_format": settings.elevenlabs_output_format,
            "voice_settings": {
                "stability": settings.elevenlabs_stability,
                "similarity_boost": settings.elevenlabs_similarity_boost,
                "style": settings.elevenlabs_style,
                "use_speaker_boost": settings.elevenlabs_speaker_boost,
            },
        }

        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.RequestError as exc:  # noqa: PERF203
            raise TTSServiceError(f"Ошибка соединения с ElevenLabs: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip()
            if len(detail) > 400:
                detail = detail[:400] + "..."
            raise TTSServiceError(f"Ошибка ElevenLabs {response.status_code}: {detail}")

        audio_bytes = bytes(response.content)
        if not audio_bytes:
            raise TTSServiceError("ElevenLabs вернул пустой аудио-ответ.")

        result = TTSResponse(tts_text=prepared_text, audio_bytes=audio_bytes, content_type="audio/mpeg")
        self._remember(cache_key, result)
        return result

    def _resolve_voice_id(self, *, language: PreferredLanguage, voice: str) -> str:
        voice = voice.strip()
        if voice and voice != "default":
            return voice
        if language == PreferredLanguage.kz and settings.elevenlabs_voice_id_kz:
            return settings.elevenlabs_voice_id_kz
        if language == PreferredLanguage.ru and settings.elevenlabs_voice_id_ru:
            return settings.elevenlabs_voice_id_ru
        if settings.elevenlabs_voice_id_ru:
            # fallback to RU voice if KZ is not configured
            return settings.elevenlabs_voice_id_ru
        return self._discover_voice_id(language=language)

    def _discover_voice_id(self, *, language: PreferredLanguage) -> str:
        lang_key = "kz" if language == PreferredLanguage.kz else "ru"
        cached = self._autodetected_voice_ids.get(lang_key)
        if cached:
            return cached

        url = f"{settings.elevenlabs_base_url.rstrip('/')}/voices"
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Accept": "application/json",
        }
        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise TTSProviderUnavailableError(f"Не удалось получить список голосов ElevenLabs: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip()
            if len(detail) > 300:
                detail = detail[:300] + "..."
            raise TTSProviderUnavailableError(
                f"Не удалось получить список голосов ElevenLabs ({response.status_code}): {detail}"
            )

        payload = response.json()
        voices = payload.get("voices", []) if isinstance(payload, dict) else []
        if not isinstance(voices, list) or not voices:
            raise TTSProviderUnavailableError("ElevenLabs не вернул доступные голоса для аккаунта.")

        preferred_tokens = (
            ("kazakh", "қазақ", "kaz", "kk")
            if language == PreferredLanguage.kz
            else ("russian", "рус", "ru", "русский")
        )

        def score_voice(item: dict[str, Any]) -> int:
            fields: list[str] = []
            fields.append(str(item.get("name", "")).lower())
            fields.append(str(item.get("description", "")).lower())
            labels = item.get("labels", {})
            if isinstance(labels, dict):
                fields.extend(str(value).lower() for value in labels.values())
            joined = " ".join(fields)
            score = 0
            for token in preferred_tokens:
                if token in joined:
                    score += 3
            if "multilingual" in joined:
                score += 1
            return score

        ranked = sorted(
            [item for item in voices if isinstance(item, dict)],
            key=score_voice,
            reverse=True,
        )
        for voice_item in ranked:
            voice_id = str(voice_item.get("voice_id", "")).strip()
            if voice_id:
                self._autodetected_voice_ids[lang_key] = voice_id
                return voice_id

        raise TTSProviderUnavailableError("Не удалось выбрать voice_id из ответа ElevenLabs.")

    @staticmethod
    def _cache_key(*, voice_id: str, model_id: str, output_format: str, text: str) -> str:
        digest = hashlib.sha256(f"{voice_id}|{model_id}|{output_format}|{text}".encode("utf-8")).hexdigest()
        return digest

    def _remember(self, key: str, value: TTSResponse) -> None:
        if key in self._cache:
            return
        self._cache[key] = value
        self._cache_order.append(key)
        while len(self._cache_order) > self._cache_limit:
            old = self._cache_order.pop(0)
            self._cache.pop(old, None)


class TTSService:
    def __init__(self) -> None:
        provider_name = settings.tts_provider.strip().lower()
        if provider_name in {"", "auto"}:
            if settings.elevenlabs_api_key:
                self._provider: TTSProvider = ElevenLabsTTSProvider()
            elif _is_edge_tts_installed():
                self._provider = EdgeTTSProvider()
            else:
                self._provider = MockTTSProvider()
            return

        if provider_name == "elevenlabs":
            self._provider: TTSProvider = ElevenLabsTTSProvider()
            return

        if provider_name in {"edge", "edge_tts"}:
            self._provider = EdgeTTSProvider()
            return

        if provider_name == "mock":
            self._provider = MockTTSProvider()
            return

        # Unknown value -> safe fallback.
        self._provider = MockTTSProvider()

    def synthesize(self, text: str, *, language: PreferredLanguage, voice: str | None = None) -> TTSResponse:
        selected_voice = (voice or settings.tts_voice).strip() or "default"
        prepared = prepare_tts_text(text)
        return self._provider.synthesize(prepared, language=language, voice=selected_voice)


def prepare_tts_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    normalized = re.sub(r"\s*([,;:])\s*", r"\1 ", normalized)
    normalized = re.sub(r"\s*([.!?…])\s*", r"\1 ", normalized)
    normalized = re.sub(r"\s+\)", ")", normalized)
    normalized = re.sub(r"\(\s+", "(", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized).strip()
    if normalized and normalized[-1] not in ".!?…":
        normalized += "."
    return normalized[:4500]


@lru_cache(maxsize=1)
def _load_edge_tts_module() -> Any | None:
    if importlib.util.find_spec("edge_tts") is None:
        return None
    import edge_tts  # type: ignore[import-not-found]

    return edge_tts


def _is_edge_tts_installed() -> bool:
    return _load_edge_tts_module() is not None


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise TTSServiceError("Edge TTS нельзя вызвать из активного event loop в синхронном контексте.")


tts_service = TTSService()
