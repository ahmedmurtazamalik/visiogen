import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from google.genai import types
import pytest

from visiogen.config import Settings
from visiogen.extractor import ExtractedDiagramGraph
from visiogen.providers.base import ExtractionValidationError, ProviderError
from visiogen.providers.gemini import GeminiExtractor


EXPECTED = Path(__file__).parents[1] / "fixtures" / "graphs" / "expected"


class FakeModels:
    def __init__(self, responses: list[object]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class FakeGeminiClient:
    def __init__(self, responses: list[object]) -> None:
        self.models = FakeModels(responses)


def gemini_settings() -> Settings:
    return Settings(
        provider="gemini",
        gemini_model="gemini-test",
        gemini_api_key="secret-test-key",
        timeout_seconds=20.0,
    )


def test_gemini_uses_structured_output_and_returns_canonical_graph() -> None:
    expected = json.loads((EXPECTED / "basic_system.json").read_text())
    client = FakeGeminiClient(
        [SimpleNamespace(text=json.dumps(expected), response_id="gemini-request-1")]
    )

    graph = GeminiExtractor(gemini_settings(), client=client).extract(
        "A sensor sends data to a processor."
    )

    assert graph.model_dump(mode="json", exclude_none=True) == expected
    assert len(client.models.calls) == 1
    call = client.models.calls[0]
    assert call["model"] == "gemini-test"
    assert call["contents"] == "A sensor sends data to a processor."
    config = call["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.temperature == 0
    assert config.response_mime_type == "application/json"
    assert config.response_schema is ExtractedDiagramGraph
    assert "geometry" in config.system_instruction.lower()
    assert "never emit" in config.system_instruction.lower()
    assert "secret-test-key" not in repr(client.models.calls)


def test_gemini_translates_sdk_failure_without_exposing_api_key() -> None:
    client = FakeGeminiClient([RuntimeError("SDK transport failed")])

    with pytest.raises(ProviderError, match="Gemini provider request failed") as error:
        GeminiExtractor(gemini_settings(), client=client).extract("A sensor system")

    assert "secret-test-key" not in str(error.value)


def test_gemini_translates_missing_text_to_provider_error() -> None:
    client = FakeGeminiClient([SimpleNamespace(text=None, response_id=None)])

    with pytest.raises(ProviderError, match="malformed response"):
        GeminiExtractor(gemini_settings(), client=client).extract("A sensor system")


def test_gemini_schema_failure_uses_one_shared_repair_attempt() -> None:
    client = FakeGeminiClient(
        [
            SimpleNamespace(text="not JSON", response_id="bad"),
            SimpleNamespace(text="still not JSON", response_id="bad-again"),
        ]
    )

    with pytest.raises(ExtractionValidationError):
        GeminiExtractor(gemini_settings(), client=client).extract("A sensor system")

    assert len(client.models.calls) == 2
    assert "Repair" in client.models.calls[1]["contents"]
