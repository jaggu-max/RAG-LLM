"""LM Studio service — OpenAI-compatible local LLM integration."""

from __future__ import annotations

from typing import AsyncGenerator, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _resolve_model(model_name: Optional[str]) -> str:
    if not model_name or model_name.lower() == "local_qwen":
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{settings.LMSTUDIO_BASE_URL}/models")
                if res.status_code == 200:
                    data = res.json()
                    models = data.get("data", [])
                    if models and len(models) > 0:
                        return models[0]["id"]
        except Exception:
            pass
        return settings.LMSTUDIO_MODEL
    return model_name


def generate(
    prompt: str,
    system_prompt: str = "",
    model_name: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """Generate a response using LM Studio (OpenAI-compatible API)."""
    model_name = _resolve_model(model_name)
    base_url = settings.LMSTUDIO_BASE_URL

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                json={
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except httpx.ConnectError:
        raise RuntimeError(
            "Local Qwen is offline. Start LM Studio and enable the local server."
        )
    except Exception as e:
        log.error("LM Studio generation error: %s", e)
        raise


async def stream_generate(
    prompt: str,
    system_prompt: str = "",
    model_name: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> AsyncGenerator[str, None]:
    """Stream a response from LM Studio."""
    model_name = _resolve_model(model_name)
    base_url = settings.LMSTUDIO_BASE_URL

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                json={
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                },
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            import json
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except Exception:
                            continue
    except httpx.ConnectError:
        yield "Error: Local Qwen is offline. Start LM Studio and enable the local server."
    except Exception as e:
        log.error("LM Studio stream error: %s", e)
        yield f"Error: {str(e)}"


def health_check() -> bool:
    """Check if LM Studio is accessible."""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{settings.LMSTUDIO_BASE_URL}/models")
            return response.status_code == 200
    except Exception:
        return False


def get_available_models() -> list[dict]:
    """Return LM Studio models."""
    is_available = health_check()
    return [{
        "id": "local_qwen",
        "name": "Local Qwen",
        "provider": "lmstudio",
        "available": is_available,
    }]
