"""Распознавание голосовых через OpenAI (иврит/русский/английский определяются автоматически)."""
from openai import AsyncOpenAI

from core.config import settings

_client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None


async def transcribe(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    if _client is None:
        raise RuntimeError("OPENAI_API_KEY не задан")
    resp = await _client.audio.transcriptions.create(
        model=settings.openai_stt_model, file=(filename, audio_bytes)
    )
    return resp.text.strip()
