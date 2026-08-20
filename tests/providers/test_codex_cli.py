import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from visiogen.config import Settings
from visiogen.extractor import ExtractedDiagramGraph
from visiogen.providers.base import ExtractionValidationError, ProviderError
from visiogen.providers.codex_cli import CodexCLIExtractor, CodexStructuredCaller

EXPECTED = Path(__file__).parents[1] / "fixtures" / "graphs" / "expected"


def codex_settings() -> Settings:
    return Settings(
        provider="codex",
        codex_model="gpt-5.6-sol-test",
        codex_command="/opt/codex",
        timeout_seconds=25.0,
    )


class FakeRunner:
    def __init__(self, responses: list[str | None | BaseException], returncodes: list[int] | None = None) -> None:
        self.responses = iter(responses)
        self.returncodes = iter(returncodes or [0] * len(responses))
        self.calls: list[dict[str, Any]] = []
        self.schemas: list[dict[str, Any]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        response = next(self.responses)
        self.calls.append({"args": args, **kwargs})
        if isinstance(response, BaseException):
            raise response
        schema_path = Path(args[args.index("--output-schema") + 1])
        self.schemas.append(json.loads(schema_path.read_text()))
        returncode = next(self.returncodes)
        if response is not None:
            output_path = Path(args[args.index("--output-last-message") + 1])
            output_path.write_text(response)
        return subprocess.CompletedProcess(args, returncode, stdout="", stderr="")


def object_schemas(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("type") == "object":
            found.append(value)
        for child in value.values():
            found.extend(object_schemas(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(object_schemas(child))
    return found


def test_codex_cli_runs_isolated_schema_constrained_extraction() -> None:
    expected = json.loads((EXPECTED / "basic_system.json").read_text())
    runner = FakeRunner([json.dumps(expected)])

    graph = CodexCLIExtractor(codex_settings(), runner=runner).extract(
        "A sensor sends data to a processor."
    )

    assert graph.model_dump(mode="json", exclude_none=True) == expected
    assert len(runner.calls) == 1
    call = runner.calls[0]
    args = call["args"]
    assert args[0:2] == ["/opt/codex", "exec"]
    assert "--ephemeral" in args
    assert "--ignore-user-config" in args
    assert "--ignore-rules" in args
    assert 'shell_environment_policy.inherit="none"' in args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--skip-git-repo-check" in args
    assert args[args.index("--model") + 1] == "gpt-5.6-sol-test"
    assert args[-1] == "-"
    assert call["timeout"] == 25.0
    assert call["text"] is True
    assert call["capture_output"] is True
    assert set(call["env"]) <= {
        "CODEX_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
    }
    assert "A sensor sends data to a processor." in call["input"]
    assert "The response must satisfy this JSON Schema" not in call["input"]
    assert not Path(call["cwd"]).exists()

    strict_objects = object_schemas(runner.schemas[0])
    assert strict_objects
    for schema in strict_objects:
        assert schema["additionalProperties"] is False
        assert schema["required"] == list(schema.get("properties", {}))


def test_codex_cli_preserves_one_shared_schema_repair_attempt() -> None:
    expected = (EXPECTED / "basic_system.json").read_text()
    runner = FakeRunner(["not JSON", expected])

    graph = CodexCLIExtractor(codex_settings(), runner=runner).extract("A sensor system")

    assert graph.title == "Sensor processing system"
    assert len(runner.calls) == 2
    assert "Repair" in runner.calls[1]["input"]


@pytest.mark.parametrize(
    ("response", "returncodes", "message"),
    [
        (FileNotFoundError(), None, "executable was not found"),
        (subprocess.TimeoutExpired("codex", 25), None, "timed out"),
        (None, [2], "exited with status 2"),
        (None, [0], "did not write a response"),
    ],
)
def test_codex_cli_translates_process_failures(
    response: str | None | BaseException,
    returncodes: list[int] | None,
    message: str,
) -> None:
    runner = FakeRunner([response], returncodes)

    with pytest.raises(ProviderError, match=message):
        CodexCLIExtractor(codex_settings(), runner=runner).extract("A sensor system")


def test_codex_cli_invalid_output_fails_after_one_repair() -> None:
    runner = FakeRunner(["not JSON", "still not JSON"])

    with pytest.raises(ExtractionValidationError):
        CodexCLIExtractor(codex_settings(), runner=runner).extract("A sensor system")

    assert len(runner.calls) == 2
    assert ExtractedDiagramGraph.model_json_schema() != runner.schemas[0]


class SmallOutput(BaseModel):
    answer: str


def test_generic_structured_caller_supports_image_input(tmp_path: Path) -> None:
    runner = FakeRunner(['{"answer":"move the processor"}'])
    image = tmp_path / "preview.png"
    image.write_bytes(b"not-a-real-image-needed-by-fake-runner")
    caller = CodexStructuredCaller(codex_settings(), SmallOutput, runner=runner)

    response = caller.call_with_images(
        "Critique the drawing. The response must satisfy this JSON Schema: {}",
        "Find visible layout problems",
        [image],
    )

    assert json.loads(response.content) == {"answer": "move the processor"}
    assert response.transport_prompt == runner.calls[0]["input"]
    args = runner.calls[0]["args"]
    assert "--image" in args
    image_arg = Path(args[args.index("--image") + 1])
    assert image_arg.name == "preview.png"
    assert not image_arg.exists()
    assert runner.schemas[0]["required"] == ["answer"]
