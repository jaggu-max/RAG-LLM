"""LM Studio service wrapper — delegates to app.providers.local_qwen_provider."""

from __future__ import annotations

from typing import AsyncGenerator, Optional
from app.providers.local_qwen_provider import local_qwen_provider


def generate(
    prompt: str,
    system_prompt: str = "",
    model_name: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """Generate a response using LocalQwenProvider."""
    return local_qwen_provider.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def stream_generate(
    prompt: str,
    system_prompt: str = "",
    model_name: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> AsyncGenerator[str, None]:
    """Stream response using LocalQwenProvider."""
    async for chunk in local_qwen_provider.stream_generate(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        yield chunk


def health_check() -> bool:
    """Check if LM Studio is accessible."""
    return local_qwen_provider.check_connection()


def get_available_models() -> list[dict]:
    """Return Ollama local models info."""
    status_info = local_qwen_provider.get_status()
    is_available = status_info["status"] == "ready"
    active_model = status_info.get("model", "gemma3:4b")
    return [{
        "id": "local_qwen",
        "name": f"Ollama ({active_model})",
        "provider": "lmstudio",
        "available": is_available,
        "active_model": active_model,
    }]


