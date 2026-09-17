"""Gemini Provider abstraction — model-agnostic dynamic model discovery, filtering, and execution."""

from __future__ import annotations

import time
from typing import AsyncGenerator, List, Optional, Tuple

import google.generativeai as genai

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

EXCLUDE_KEYWORDS = [
    "embedding", "embed", "imagen", "image", "tts", "audio",
    "transcribe", "video", "computer-use", "robotics", "deep-research",
    "lyria", "banana",
]


class GeminiProvider:
    """Model-agnostic Gemini Provider managing dynamic model discovery and execution."""

    def __init__(self):
        self._cached_model_name: Optional[str] = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl_seconds: float = 900.0

    def _get_api_key(self, custom_key: Optional[str] = None) -> str:
        key = custom_key or settings.GEMINI_API_KEY
        if not key or not key.strip():
            raise RuntimeError("Invalid Gemini API key. Please check your API key.")
        return key.strip()

    def discover_models(self, api_key: str) -> List[str]:
        """Discover available text-generation models for the given API key."""
        try:
            genai.configure(api_key=api_key)
            all_models = genai.list_models()

            compatible_models: List[str] = []
            for m in all_models:
                m_name = m.name.replace("models/", "").lower()
                if "generateContent" not in getattr(m, "supported_generation_methods", []):
                    continue
                if any(kw in m_name for kw in EXCLUDE_KEYWORDS):
                    continue
                compatible_models.append(m.name.replace("models/", ""))

            def rank_model(name: str) -> int:
                name_l = name.lower()
                if "3.6-flash" in name_l: return 0
                if "3.7-flash" in name_l: return 1
                if "2.0-flash" in name_l: return 2
                if "1.5-flash" in name_l: return 3
                if "flash" in name_l: return 4
                if "pro" in name_l: return 5
                return 10

            compatible_models.sort(key=rank_model)
            return compatible_models

        except Exception as e:
            err_str = str(e)
            if "401" in err_str or "403" in err_str or "API_KEY_INVALID" in err_str:
                raise RuntimeError("Invalid Gemini API key. Please check your API key.")
            if "429" in err_str or "ResourceExhausted" in err_str:
                raise RuntimeError("Gemini quota exceeded. Please use another Gemini API key or wait for your quota to reset.")
            raise RuntimeError(f"Failed to discover Gemini models: {err_str}")

    def get_selected_model(self, api_key: str, force_refresh: bool = False) -> str:
        """Get or discover the best available Gemini model."""
        now = time.time()
        if not force_refresh and self._cached_model_name and (now - self._cache_timestamp) < self._cache_ttl_seconds:
            return self._cached_model_name

        models = self.discover_models(api_key)
        if not models:
            raise RuntimeError("No compatible Gemini model is available for this API key/project.")

        selected = models[0]
        self._cached_model_name = selected
        self._cache_timestamp = now
        return selected

    def test_connection(self, custom_key: Optional[str] = None) -> Tuple[str, str]:
        """Test API key connection and return status."""
        try:
            key = self._get_api_key(custom_key)
            models = self.discover_models(key)
            if not models:
                return "Unavailable", "No compatible Gemini model is available for this API key/project."
            test_model = models[0]
            genai.configure(api_key=key)
            model_obj = genai.GenerativeModel(test_model)
            res = model_obj.generate_content("hi", generation_config={"max_output_tokens": 5})
            if res:
                return "Ready", "Gemini API key is valid and ready."
            return "Ready", "Gemini API key connected."
        except Exception as e:
            err_str = str(e)
            if "Invalid Gemini API key" in err_str or "401" in err_str or "403" in err_str or "API_KEY_INVALID" in err_str:
                return "Invalid API Key", "Invalid Gemini API key. Please check your API key."
            if "quota exceeded" in err_str.lower() or "429" in err_str or "ResourceExhausted" in err_str:
                return "Quota Exceeded", "Gemini quota exceeded. Please use another Gemini API key or wait for your quota to reset."
            return "Unavailable", f"Gemini service unavailable: {err_str}"

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2048,
        custom_key: Optional[str] = None,
    ) -> str:
        """Generate response using dynamic model discovery."""
        key = self._get_api_key(custom_key)
        genai.configure(api_key=key)
        model_name = self.get_selected_model(key)
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        try:
            model_obj = genai.GenerativeModel(model_name)
            res = model_obj.generate_content(
                full_prompt,
                generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
            )
            if res and res.text:
                return res.text.strip()
            return "No response generated."
        except Exception as first_err:
            try:
                model_name = self.get_selected_model(key, force_refresh=True)
                model_obj = genai.GenerativeModel(model_name)
                res = model_obj.generate_content(
                    full_prompt,
                    generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
                )
                if res and res.text:
                    return res.text.strip()
            except Exception as retry_err:
                raise RuntimeError(str(retry_err)) from retry_err
            raise RuntimeError(str(first_err)) from first_err

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2048,
        custom_key: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response using dynamic Gemini model."""
        try:
            key = self._get_api_key(custom_key)
            genai.configure(api_key=key)
            model_name = self.get_selected_model(key)
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            model_obj = genai.GenerativeModel(model_name)
            response = model_obj.generate_content(
                full_prompt,
                generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
                stream=True,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as err:
            yield f"Error: {str(err)}"


gemini_provider = GeminiProvider()
