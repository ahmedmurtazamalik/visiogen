import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from visiogen.config import Settings
from visiogen.providers.base import ExtractionValidationError, ProviderError
from visiogen.providers.local_qwen import LocalQwenExtractor


EXPECTED = Path(__file__).parents[1] / "fixtures" / "graphs" / "expected"


def local_settings() -> Settings:
    return Settings(
        provider="local",
        local_base_url="http://127.0.0.1:8080/v1",
        local_model="qwen-test",
        timeout_seconds=25.0,
    )


class FakeClient:
    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"url": url, **kwargs})
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def completion_response(content: str, *, status: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "http://local/v1/chat/completions")
    return httpx.Response(
        status,
        json={"choices": [{"message": {"content": content}}]},
        headers={"x-request-id": "local-request-1"},
        request=request,
    )


def test_local_qwen_builds_json_only_request_and_returns_canonical_graph() -> None:
    expected = json.loads((EXPECTED / "basic_system.json").read_text())
    client = FakeClient([completion_response(json.dumps(expected))])

    graph = LocalQwenExtractor(local_settings(), client=client).extract(
        "A sensor sends data to a processor."
    )

    assert graph.model_dump(mode="json", exclude_none=True) == expected
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert request["timeout"] == 25.0
    assert request["json"]["model"] == "qwen-test"
    assert request["json"]["temperature"] == 0
    assert request["json"]["response_format"] == {"type": "json_object"}
    assert [message["role"] for message in request["json"]["messages"]] == [
        "system",
        "user",
    ]


def test_local_qwen_translates_http_failure_to_provider_error() -> None:
    client = FakeClient([completion_response("ignored", status=503)])

    with pytest.raises(ProviderError, match="HTTP 503"):
        LocalQwenExtractor(local_settings(), client=client).extract("A sensor system")


def test_local_qwen_translates_transport_failure_to_provider_error() -> None:
    request = httpx.Request("POST", "http://127.0.0.1:8080/v1/chat/completions")
    client = FakeClient([httpx.ConnectError("connection refused", request=request)])

    with pytest.raises(ProviderError, match="transport failed"):
        LocalQwenExtractor(local_settings(), client=client).extract("A sensor system")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(
            200,
            json={"unexpected": True},
            request=httpx.Request("POST", "http://local/v1/chat/completions"),
        ),
        httpx.Response(
            200,
            text="not JSON",
            request=httpx.Request("POST", "http://local/v1/chat/completions"),
        ),
    ],
)
def test_local_qwen_translates_malformed_response_envelope(
    response: httpx.Response,
) -> None:
    with pytest.raises(ProviderError, match="malformed response"):
        LocalQwenExtractor(local_settings(), client=FakeClient([response])).extract(
            "A sensor system"
        )


def test_local_qwen_schema_failure_uses_one_shared_repair_attempt() -> None:
    client = FakeClient(
        [completion_response("not JSON"), completion_response("still not JSON")]
    )

    with pytest.raises(ExtractionValidationError):
        LocalQwenExtractor(local_settings(), client=client).extract("A sensor system")

    assert len(client.calls) == 2
    assert "Repair" in client.calls[1]["json"]["messages"][1]["content"]
