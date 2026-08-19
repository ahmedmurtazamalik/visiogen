import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import httpx
import pytest

from visiogen.config import Settings
from visiogen.models import DiagramGraph
from visiogen.providers.base import DiagramExtractor, NoDiagramContentError
from visiogen.providers.gemini import GeminiExtractor
from visiogen.providers.local_qwen import LocalQwenExtractor


FIXTURES = Path(__file__).parents[1] / "fixtures"
EXPECTED = FIXTURES / "graphs" / "expected"
CASES = [
    "linear_flow",
    "login_decision",
    "method_loop",
    "isolated_process",
    "ambiguous_no_diagram",
    "basic_system",
    "bidirectional_architecture",
    "nested_subsystem",
    "eco_headphone",
    "patent_schematic",
]
ProviderName = Literal["local", "gemini"]


class ContractHttpClient:
    def __init__(self, content: str) -> None:
        self.content = content

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": self.content}}]},
            request=httpx.Request("POST", url),
        )


class ContractModels:
    def __init__(self, content: str) -> None:
        self.content = content

    def generate_content(self, **kwargs: Any) -> object:
        return SimpleNamespace(text=self.content, response_id="contract-request")


class ContractGeminiClient:
    def __init__(self, content: str) -> None:
        self.models = ContractModels(content)


def make_extractor(provider: ProviderName, content: str) -> DiagramExtractor:
    if provider == "local":
        return LocalQwenExtractor(
            Settings(provider="local", local_model="contract-model"),
            client=ContractHttpClient(content),
        )
    return GeminiExtractor(
        Settings(
            provider="gemini",
            gemini_model="contract-model",
            gemini_api_key="contract-key",
        ),
        client=ContractGeminiClient(content),
    )


@pytest.mark.parametrize("provider", ["local", "gemini"])
@pytest.mark.parametrize("case", CASES)
def test_both_providers_share_the_reviewed_fixture_contract(
    provider: ProviderName, case: str
) -> None:
    text = (FIXTURES / "text" / f"{case}.txt").read_text()
    if case == "ambiguous_no_diagram":
        content = json.dumps(
            {
                "title": "No diagram",
                "diagram_type": "flowchart",
                "orientation": "top_to_bottom",
                "nodes": [],
                "edges": [],
            }
        )
        with pytest.raises(NoDiagramContentError):
            make_extractor(provider, content).extract(text)
        return

    expected = DiagramGraph.model_validate_json((EXPECTED / f"{case}.json").read_text())
    actual = make_extractor(provider, expected.model_dump_json(exclude_none=True)).extract(
        text
    )

    assert actual == expected
    assert actual.has_geometry is False
