"""Local Qwen Provider — OpenAI-compatible local model integration via LM Studio."""

from __future__ import annotations

import time
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class LocalQwenProvider:
    """Local Qwen Provider managing model discovery, execution, and error handling for Ollama."""

    def __init__(self, base_url: Optional[str] = None):
        default_url = getattr(settings, "OLLAMA_BASE_URL", getattr(settings, "LMSTUDIO_BASE_URL", "http://127.0.0.1:11434/v1"))
        self._base_url = (base_url or default_url).rstrip("/")
        self._cached_model_id: Optional[str] = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl_seconds: float = 30.0

    @property
    def base_url(self) -> str:
        return self._base_url

    def check_connection(self) -> bool:
        """Check if Ollama API server is online."""
        root_url = self._base_url.replace("/v1", "").rstrip("/")
        # Try native Ollama endpoint GET /api/tags first
        try:
            with httpx.Client(timeout=3.0) as client:
                res_tags = client.get(f"{root_url}/api/tags")
                if res_tags.status_code == 200:
                    return True
        except Exception:
            pass

        # Try OpenAI-compatible endpoint GET /v1/models
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self._base_url}/models")
                return res.status_code == 200
        except Exception:
            pass

        return False

    def discover_models(self, force_refresh: bool = False) -> List[str]:
        """Discover available models from Ollama /api/tags or /v1/models."""
        now = time.time()
        if not force_refresh and self._cached_model_id and (now - self._cache_timestamp) < self._cache_ttl_seconds:
            return [self._cached_model_id]

        model_ids: List[str] = []
        root_url = self._base_url.replace("/v1", "").rstrip("/")

        # 1. Try native Ollama GET /api/tags first
        try:
            with httpx.Client(timeout=5.0) as client:
                res_tags = client.get(f"{root_url}/api/tags")
                if res_tags.status_code == 200:
                    tags_data = res_tags.json()
                    model_ids = [m.get("name") for m in tags_data.get("models", []) if m.get("name")]
        except Exception as e:
            log.debug("Ollama /api/tags check failed: %s", e)

        # 2. Fallback to OpenAI-compatible endpoint GET /v1/models
        if not model_ids:
            try:
                with httpx.Client(timeout=5.0) as client:
                    res = client.get(f"{self._base_url}/models")
                    if res.status_code == 200:
                        data = res.json()
                        raw_models = data.get("data", [])
                        model_ids = [m.get("id") for m in raw_models if m.get("id")]
            except Exception as e:
                log.debug("Ollama /v1/models check failed: %s", e)

        if not model_ids:
            log.warning("Ollama server is offline or has no loaded models at %s", root_url)
            return []

        # Rank models: prefer Qwen, instruct/chat models, loaded models
        def rank_model(m_id: str) -> int:
            l_id = m_id.lower()
            if "qwen" in l_id and ("instruct" in l_id or "chat" in l_id):
                return 0
            if "qwen" in l_id:
                return 1
            if "instruct" in l_id or "chat" in l_id or "gemma" in l_id:
                return 2
            return 5

        model_ids.sort(key=rank_model)
        if model_ids:
            self._cached_model_id = model_ids[0]
            self._cache_timestamp = now
            log.info("Discovered Local Qwen (Ollama) model: %s", self._cached_model_id)

        return model_ids


    def get_selected_model(self, force_refresh: bool = False) -> str:
        """Get the active local model ID or raise user-friendly error."""
        models = self.discover_models(force_refresh=force_refresh)
        if not models:
            if not self.check_connection():
                raise RuntimeError("Local Qwen (Ollama) is offline. Start the Ollama server.")
            raise RuntimeError("No local model is available in Ollama.")
        return models[0]

    def get_status(self) -> Dict[str, str]:
        """Return provider status and active model ID."""
        try:
            models = self.discover_models()
            if models:
                return {
                    "provider": "local_qwen",
                    "status": "ready",
                    "model": models[0],
                }
            if self.check_connection():
                return {
                    "provider": "local_qwen",
                    "status": "no_models",
                    "model": "None",
                }
            return {
                "provider": "local_qwen",
                "status": "offline",
                "model": "None",
            }
        except Exception:
            return {
                "provider": "local_qwen",
                "status": "offline",
                "model": "None",
            }

    def format_error_message(self, err: Exception) -> str:
        """Format raw exceptions into friendly user-facing messages."""
        if isinstance(err, httpx.ConnectError) or "ConnectError" in str(type(err)):
            return "Local Qwen (Ollama) is offline. Start the Ollama server."
        if isinstance(err, httpx.TimeoutException) or "Timeout" in str(type(err)):
            return "Local Qwen (Ollama) took too long to respond."

        err_str = str(err)
        if "503" in err_str or "loading" in err_str.lower():
            return "Local Qwen model is still loading. Please try again."
        if "404" in err_str or "No local model" in err_str:
            return "No local model is available in Ollama."
        if "Local Qwen (Ollama) is offline" in err_str or "Local Qwen is offline" in err_str:
            return err_str

        return f"Local Qwen (Ollama) error: {err_str}"


    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        """Generate response using Ollama /v1/chat/completions or native /api/chat."""
        model_id = model_name if (model_name and model_name.lower() != "local_qwen" and model_name.lower() != "gemini") else self.get_selected_model()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        try:
            with httpx.Client(timeout=120.0) as client:
                # 1. Try OpenAI-compatible endpoint
                try:
                    res = client.post(f"{self._base_url}/chat/completions", json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        choices = data.get("choices", [])
                        if choices and len(choices) > 0:
                            content = choices[0].get("message", {}).get("content", "")
                            if content:
                                return content.strip()
                except Exception as e:
                    log.warning("OpenAI-compatible endpoint failed: %s. Trying native /api/chat", e)

                # 2. Fallback to native Ollama POST /api/chat
                root_url = self._base_url.replace("/v1", "")
                native_payload = {
                    "model": model_id,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature},
                }
                res_native = client.post(f"{root_url}/api/chat", json=native_payload)
                res_native.raise_for_status()
                data_native = res_native.json()
                content = data_native.get("message", {}).get("content", "")
                if content:
                    return content.strip()

                return "No response returned from Local Qwen / Ollama."

        except Exception as e:
            err_msg = self.format_error_message(e)
            log.error("LocalQwenProvider generate error: %s", err_msg)
            raise RuntimeError(err_msg) from e

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Stream response from Ollama /v1/chat/completions or native /api/chat."""
        try:
            model_id = model_name if (model_name and model_name.lower() != "local_qwen" and model_name.lower() != "gemini") else self.get_selected_model()
        except Exception as e:
            yield f"Error: {self.format_error_message(e)}"
            return

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                root_url = self._base_url.replace("/v1", "")
                native_payload = {
                    "model": model_id,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": temperature},
                }
                async with client.stream("POST", f"{root_url}/api/chat", json=native_payload) as res:
                    if res.status_code != 200:
                        yield f"Error: {self.format_error_message(RuntimeError(f'HTTP {res.status_code}'))}"
                        return
                    async for line in res.aiter_lines():
                        if line:
                            try:
                                import json
                                data = json.loads(line)
                                text = data.get("message", {}).get("content", "")
                                if text:
                                    yield text
                            except Exception:
                                continue
        except Exception as e:
            err_msg = self.format_error_message(e)
            log.error("LocalQwenProvider stream error: %s", err_msg)
            yield f"Error: {err_msg}"



# Global singleton instance
local_qwen_provider = LocalQwenProvider()
