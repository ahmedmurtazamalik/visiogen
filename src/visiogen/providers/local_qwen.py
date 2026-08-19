"""OpenAI-compatible local Qwen extraction provider."""

from __future__ import annotations

from time import monotonic
from typing import Any, Protocol

import httpx

from visiogen.config import Settings
from visiogen.extractor import StructuredExtractionWorkflow
from visiogen.models import DiagramGraph
from visiogen.providers.base import ProviderError, ProviderResponse


class HttpClient(Protocol):
    def post(self, url: str, **kwargs: Any) -> httpx.Response: ...


class LocalQwenExtractor:
    """Extract canonical semantics through an OpenAI-compatible local endpoint."""

    def __init__(self, settings: Settings, *, client: HttpClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client()
        self._workflow = StructuredExtractionWorkflow(self._call_model)

    def extract(self, text: str) -> DiagramGraph:
        return self._workflow.extract(text)

    def _call_model(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        started = monotonic()
        try:
            response = self._client.post(
                f"{self._settings.local_base_url}/chat/completions",
                json={
                    "model": self._settings.local_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0,
                    "top_p": 0.1,
                    "response_format": {"type": "json_object"},
                },
                timeout=self._settings.timeout_seconds,
            )
        except httpx.RequestError as error:
            raise ProviderError("Local Qwen provider transport failed") from error
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise ProviderError(
                f"Local Qwen provider returned HTTP {error.response.status_code}"
            ) from error
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("completion content is not text")
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProviderError("Local Qwen provider returned a malformed response") from error
        return ProviderResponse(
            content=content,
            request_id=response.headers.get("x-request-id"),
            elapsed_ms=(monotonic() - started) * 1000,
        )
