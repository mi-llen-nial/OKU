from dataclasses import dataclass


@dataclass
class STTResponse:
    transcript: str
    confidence: float


class STTProvider:
    def transcribe(self, audio_blob: bytes | None) -> STTResponse:
        raise NotImplementedError


class MockSTTProvider(STTProvider):
    def transcribe(self, audio_blob: bytes | None) -> STTResponse:
        # Prototyping placeholder: real provider can replace this class later.
        return STTResponse(transcript="[mock transcript]", confidence=0.5)
