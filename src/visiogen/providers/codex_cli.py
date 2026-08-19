"""Schema-constrained extraction through the authenticated Codex CLI."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, Callable

from visiogen.config import Settings
from visiogen.extractor import ExtractedDiagramGraph, StructuredExtractionWorkflow
from visiogen.models import DiagramGraph
from visiogen.providers.base import ProviderError, ProviderResponse


ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]
_SCHEMA_PROMPT_MARKER = " The response must satisfy this JSON Schema:"


def _strict_output_schema() -> dict[str, Any]:
    """Adapt Pydantic JSON Schema to Codex's strict-output requirements."""

    schema = deepcopy(ExtractedDiagramGraph.model_json_schema())

    def require_all_properties(value: Any) -> None:
        if isinstance(value, dict):
            properties = value.get("properties")
            if value.get("type") == "object" and isinstance(properties, dict):
                value["required"] = list(properties)
                value["additionalProperties"] = False
            for child in value.values():
                require_all_properties(child)
        elif isinstance(value, list):
            for child in value:
                require_all_properties(child)

    require_all_properties(schema)
    return schema


def _prompt_without_embedded_schema(system_prompt: str, user_prompt: str) -> str:
    instructions = system_prompt.split(_SCHEMA_PROMPT_MARKER, 1)[0]
    return (
        "Act only as a structured diagram extraction engine. Do not inspect files, "
        "run commands, edit anything, or explain the answer. "
        f"{instructions}\n\nInput description:\n{user_prompt}\n"
        "Return only the schema-conforming final response."
    )


class CodexCLIExtractor:
    """Extract canonical semantics through an isolated local Codex CLI process."""

    def __init__(
        self,
        settings: Settings,
        *,
        runner: ProcessRunner | None = None,
    ) -> None:
        self._settings = settings
        self._runner = runner or subprocess.run
        self._workflow = StructuredExtractionWorkflow(self._call_model)

    def extract(self, text: str) -> DiagramGraph:
        return self._workflow.extract(text)

    def _call_model(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        started = monotonic()
        prompt = _prompt_without_embedded_schema(system_prompt, user_prompt)
        with TemporaryDirectory(prefix="visiogen-codex-") as directory:
            workdir = Path(directory)
            schema_path = workdir / "output-schema.json"
            output_path = workdir / "response.json"
            schema_path.write_text(json.dumps(_strict_output_schema(), indent=2) + "\n")
            command = [
                self._settings.codex_command,
                "exec",
                "--ephemeral",
                "--ignore-rules",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--cd",
                str(workdir),
                "--model",
                self._settings.codex_model,
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
            try:
                completed = self._runner(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self._settings.timeout_seconds,
                    cwd=workdir,
                )
            except FileNotFoundError as error:
                raise ProviderError("Codex CLI executable was not found") from error
            except subprocess.TimeoutExpired as error:
                raise ProviderError("Codex CLI extraction timed out") from error
            except OSError as error:
                raise ProviderError("Codex CLI process could not be started") from error

            if completed.returncode != 0:
                raise ProviderError(
                    f"Codex CLI exited with status {completed.returncode}"
                )
            if not output_path.is_file():
                raise ProviderError("Codex CLI did not write a response")
            try:
                content = output_path.read_text()
            except OSError as error:
                raise ProviderError("Codex CLI response could not be read") from error

        return ProviderResponse(
            content=content,
            elapsed_ms=(monotonic() - started) * 1000,
        )
