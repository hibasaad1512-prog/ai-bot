from __future__ import annotations
import json
import logging
from typing import Any
from .base import AIProvider
from .schemas import DECISION_SCHEMA
from app.config import settings

log = logging.getLogger(__name__)


class GroqProvider(AIProvider):
    """Groq text/structured-output provider.

    Groq is used for all text + decision generation. Image generation/vision
    are intentionally reported as unsupported by this provider rather than
    pretending they work.
    """

    def __init__(self):
        self.client = None
        if settings.groq_api_key:
            try:
                from groq import Groq
                self.client = Groq(api_key=settings.groq_api_key)
            except Exception:
                log.exception("Groq init failed")

    @property
    def enabled(self) -> bool:
        return self.client is not None

    @staticmethod
    def _messages(prompt: str, system: str | None = None):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _call(self, prompt: str, system: str | None = None, response_format: dict[str, Any] | None = None):
        if not self.client:
            raise RuntimeError("Groq is not configured")
        kwargs: dict[str, Any] = {
            "model": settings.groq_text_model,
            "messages": self._messages(prompt, system),
            "temperature": 0.8,
            "max_tokens": 1200,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        return self.client.chat.completions.create(**kwargs)

    def generate_text(self, prompt: str, system: str | None = None) -> str:
        response = self._call(prompt, system)
        content = response.choices[0].message.content or ""
        return content.strip()

    def generate_structured(self, prompt: str, schema: dict[str, Any], system: str | None = None) -> dict[str, Any]:
        # Strict JSON schema is supported by current Groq structured outputs.
        # Make every object closed because strict schemas require it.
        structured_schema = dict(DECISION_SCHEMA)
        structured_schema["additionalProperties"] = False
        response = self._call(
            prompt,
            system,
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "kyoos_decision",
                    "strict": True,
                    "schema": structured_schema,
                },
            },
        )
        raw = response.choices[0].message.content or "{}"
        return json.loads(raw)

    def analyze_image(self, image_bytes: bytes, prompt: str) -> str:
        raise RuntimeError("Groq provider does not expose image vision in this bot build")

    def generate_image(self, prompt: str) -> bytes | None:
        return None
