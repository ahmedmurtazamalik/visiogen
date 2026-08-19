"""Google Gemini structured-output extraction provider."""

from __future__ import annotations

from time import monotonic
from typing import Any, Protocol

from google import genai
from google.genai import types

from visiogen.config import Settings
from visiogen.extractor import ExtractedDiagramGraph, StructuredExtractionWorkflow
from visiogen.models import DiagramGraph
from visiogen.providers.base import ProviderError, ProviderResponse


class GeminiModels(Protocol):
    def generate_content(self, **kwargs: Any) -> object: ...


class GeminiClient(Protocol):
    @property
    def models(self) -> GeminiModels: ...


class GeminiExtractor:
    """Extract canonical semantics using Gemini structured JSON output."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: GeminiClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(settings.timeout_seconds * 1000)),
        )
        self._workflow = StructuredExtractionWorkflow(self._call_model)

    def extract(self, text: str) -> DiagramGraph:
        return self._workflow.extract(text)

    def _call_model(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        started = monotonic()
        try:
            response = self._client.models.generate_content(
                model=self._settings.gemini_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0,
                    response_mime_type="application/json",
                    response_json_schema=ExtractedDiagramGraph.model_json_schema(),
                ),
            )
        except Exception as error:
            raise ProviderError("Gemini provider request failed") from error
        content = getattr(response, "text", None)
        if not isinstance(content, str):
            raise ProviderError("Gemini provider returned a malformed response")
        request_id = getattr(response, "response_id", None)
        return ProviderResponse(
            content=content,
            request_id=request_id,
            elapsed_ms=(monotonic() - started) * 1000,
        )
