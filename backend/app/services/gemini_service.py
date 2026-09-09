"""Gemini LLM service — Google Generative AI integration using model-agnostic GeminiProvider."""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from app.services.gemini_provider import gemini_provider


def generate(
    prompt: str,
    system_prompt: str = "",
    model_name: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """Generate a response using GeminiProvider."""
    return gemini_provider.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def stream_generate(
    prompt: str,
    system_prompt: str = "",
    model_name: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> AsyncGenerator[str, None]:
    """Stream a response using GeminiProvider."""
    async for chunk in gemini_provider.stream_generate(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        yield chunk


def health_check() -> bool:
    """Check if Gemini API Key status is Ready."""
    status, _ = gemini_provider.test_connection()
    return status == "Ready"


def get_available_models() -> list[dict]:
    """Return unified Gemini entry with dynamic connection status."""
    status, message = gemini_provider.test_connection()
    return [
        {
            "id": "gemini",
            "name": "Gemini",
            "provider": "gemini",
            "available": status == "Ready",
            "status": status,
            "status_message": message,
        }
    ]
