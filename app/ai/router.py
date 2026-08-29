from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

from .base import AIProvider
from .groq import GroqProvider
from .gemini import GeminiProvider

log = logging.getLogger(__name__)


class OpenAICompatibleProvider(AIProvider):
    """Dependency-light adapter for OpenAI-compatible chat APIs."""

    def __init__(self, name: str, api_key: str, base_url: str, model: str):
        self.name = name
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.model)

    def _request(self, messages: list[dict[str, Any]], **extra) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError(f"{self.name} is not configured")
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "messages": messages, **extra},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def _messages(self, prompt: str, system: str | None) -> list[dict[str, str]]:
        result = []
        if system:
            result.append({"role": "system", "content": system})
        result.append({"role": "user", "content": prompt})
        return result

    def generate_text(self, prompt: str, system: str | None = None) -> str:
        data = self._request(self._messages(prompt, system), temperature=1.0)
        return str(data["choices"][0]["message"].get("content", "")).strip()

    def generate_structured(self, prompt: str, schema: dict[str, Any], system: str | None = None) -> dict[str, Any]:
        data = self._request(
            self._messages(prompt, system),
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(data["choices"][0]["message"].get("content", "{}"))

    def analyze_image(self, image_bytes: bytes, prompt: str) -> str:
        raise RuntimeError(f"{self.name} image analysis is not configured")

    def generate_image(self, prompt: str) -> bytes | None:
        return None


class MultiProvider(AIProvider):
    """Single AI interface. Every provider receives the exact same bot prompt/context."""

    def __init__(self, db):
        self.db = db
        self.groq = GroqProvider(db)
        self.providers: dict[str, AIProvider] = {"groq": self.groq}

        self._add_compatible("openai", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "https://api.openai.com/v1", "gpt-4o-mini")
        self._add_compatible("deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "https://api.deepseek.com/v1", "deepseek-chat")
        self._add_compatible("openrouter", "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "OPENROUTER_MODEL", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini")
        self._add_compatible("together", "TOGETHER_API_KEY", "TOGETHER_BASE_URL", "TOGETHER_MODEL", "https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo")

        try:
            gemini = GeminiProvider()
            if gemini.enabled:
                self.providers["gemini"] = gemini
        except Exception:
            log.exception("Gemini provider initialization failed")

        configured = os.getenv("AI_PROVIDER_ORDER", "groq,openai,deepseek,openrouter,together,gemini")
        requested = [x.strip().lower() for x in configured.split(",") if x.strip()]
        self.order = [x for x in requested if x in self.providers]
        for name in self.providers:
            if name not in self.order:
                self.order.append(name)

    def _add_compatible(self, name, key_env, base_env, model_env, default_base, default_model):
        key = os.getenv(key_env, "").strip()
        if key:
            self.providers[name] = OpenAICompatibleProvider(
                name, key, os.getenv(base_env, default_base).strip(), os.getenv(model_env, default_model).strip()
            )

    @property
    def enabled(self) -> bool:
        return any(getattr(self.providers.get(name), "enabled", False) for name in self.order)

    # Backwards compatibility for the existing owner key panel.
    @property
    def keys(self): return self.groq.keys
    @property
    def key_status(self): return self.groq.key_status
    @property
    def current_key_number(self): return self.groq.current_key_number
    def mask_key(self, key): return self.groq.mask_key(key)
    def add_key(self, key): return self.groq.add_key(key)
    def delete_key(self, index): return self.groq.delete_key(index)

    def _try(self, method: str, *args, **kwargs):
        errors = []
        for name in self.order:
            provider = self.providers.get(name)
            if not provider or not getattr(provider, "enabled", False):
                continue
            try:
                result = getattr(provider, method)(*args, **kwargs)
                if result:
                    return result
            except Exception as exc:
                errors.append(f"{name}:{type(exc).__name__}")
                log.warning("AI provider %s failed; trying next provider", name)
        raise RuntimeError("All configured AI providers failed: " + ", ".join(errors))

    def generate_text(self, prompt: str, system: str | None = None) -> str:
        return self._try("generate_text", prompt, system)

    def generate_structured(self, prompt: str, schema: dict[str, Any], system: str | None = None) -> dict[str, Any]:
        return self._try("generate_structured", prompt, schema, system)

    def analyze_image(self, image_bytes: bytes, prompt: str) -> str:
        return self._try("analyze_image", image_bytes, prompt)

    def generate_image(self, prompt: str) -> bytes | None:
        for name in self.order:
            provider = self.providers.get(name)
            if not provider or not getattr(provider, "enabled", False):
                continue
            try:
                result = provider.generate_image(prompt)
                if result:
                    return result
            except Exception:
                log.warning("AI image provider %s failed; trying next", name)
        return None

    def provider_status(self):
        return [(name, bool(getattr(self.providers.get(name), "enabled", False))) for name in self.order]
