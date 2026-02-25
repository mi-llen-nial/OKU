from dataclasses import dataclass


@dataclass
class TTSResponse:
    tts_text: str
    audio_url: str


class TTSProvider:
    def synthesize(self, text: str, *, voice: str = "default") -> TTSResponse:
        raise NotImplementedError


class MockTTSProvider(TTSProvider):
    def synthesize(self, text: str, *, voice: str = "default") -> TTSResponse:
        # Placeholder URL for future real TTS integration.
        return TTSResponse(tts_text=text, audio_url=f"mock://tts/{voice}/{len(text)}")
