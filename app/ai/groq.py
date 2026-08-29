from __future__ import annotations

import json
import logging
from typing import Any

from .base import AIProvider
from .schemas import DECISION_SCHEMA
from app.config import settings

log = logging.getLogger(__name__)


class GroqProvider(AIProvider):
    """Groq text provider for الميرفاوية.

    The runtime uses the normal text endpoint for replies.
    Structured output is kept for compatibility with the social/chaos modules.
    Image generation and vision are unsupported in this build.
    """

    def __init__(self):
        self.client = None

        if settings.groq_api_key:
            try:
                from groq import Groq

                self.client = Groq(
                    api_key=settings.groq_api_key,
                    timeout=30.0,
                    max_retries=1,
                )
            except Exception:
                log.exception("Groq initialization failed")

    @property
    def enabled(self) -> bool:
        return self.client is not None

    @staticmethod
    def _messages(
        prompt: str,
        system: str | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []

        if system:
            messages.append({
                "role": "system",
                "content": system,
            })

        messages.append({
            "role": "user",
            "content": prompt,
        })

        return messages

    def _call(
        self,
        prompt: str,
        system: str | None = None,
        response_format: dict[str, Any] | None = None,
    ):
        if not self.client:
            raise RuntimeError("Groq is not configured")

        kwargs: dict[str, Any] = {
            "model": settings.groq_text_model,
            "messages": self._messages(prompt, system),
            "temperature": 0.8,
            "max_tokens": 400,
        }

        if settings.groq_text_model.startswith("openai/gpt-oss-"):
            kwargs["reasoning_effort"] = "low"

        if response_format is not None:
            kwargs["response_format"] = response_format

        return self.client.chat.completions.create(**kwargs)

    def generate_text(
        self,
        prompt: str,
        system: str | None = None,
    ) -> str:
        response = self._call(prompt, system)

        content = response.choices[0].message.content or ""

        return content.strip()

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        system: str | None = None,
    ) -> dict[str, Any]:
        """Generate a strict structured decision for الميرفاوية."""

        structured_schema = dict(DECISION_SCHEMA)
        structured_schema["additionalProperties"] = False

        response = self._call(
            prompt,
            system,
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "Lmyrfawya_decision",
                    "strict": True,
                    "schema": structured_schema,
                },
            },
        )

        raw = response.choices[0].message.content or "{}"

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.exception("Invalid structured response from Groq")
            return {}

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
    ) -> str:
        raise RuntimeError(
            "Groq provider does not expose image vision in this bot build"
        )

    def generate_image(
        self,
        prompt: str,
    ) -> bytes | None:
        return None
