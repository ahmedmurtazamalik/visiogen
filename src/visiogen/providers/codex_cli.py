"""Schema-constrained structured model calls through authenticated Codex CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any

from pydantic import BaseModel

from visiogen.config import Settings
from visiogen.extractor import ExtractedDiagramGraph, StructuredExtractionWorkflow
from visiogen.models import DiagramGraph
from visiogen.providers.base import ProviderError, ProviderResponse

ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]
_SCHEMA_PROMPT_MARKER = " The response must satisfy this JSON Schema:"
_ALLOWED_ENVIRONMENT_KEYS = (
    "CODEX_HOME",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
)


def _subprocess_environment() -> dict[str, str]:
    """Pass only runtime/auth essentials, never the caller's arbitrary secrets."""

    return {
        key: os.environ[key]
        for key in _ALLOWED_ENVIRONMENT_KEYS
        if key in os.environ
    }


def _strict_output_schema(output_model: type[BaseModel]) -> dict[str, Any]:
    """Adapt any Pydantic JSON Schema to Codex strict-output requirements."""

    schema = deepcopy(output_model.model_json_schema())

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
        "Act only as the requested structured-response engine. Do not inspect unrelated files, "
        "run commands, edit anything, or explain outside the final structured response. "
        f"{instructions}\n\nRequest:\n{user_prompt}\n"
        "Return only the schema-conforming final response."
    )


class CodexStructuredCaller:
    """Reusable isolated Codex structured-output boundary with optional images."""

    def __init__(
        self,
        settings: Settings,
        output_model: type[BaseModel],
        *,
        runner: ProcessRunner | None = None,
    ) -> None:
        self._settings = settings
        self._output_model = output_model
        self._runner = runner or subprocess.run

    def __call__(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        return self.call_with_images(system_prompt, user_prompt, ())

    def call_with_images(
        self,
        system_prompt: str,
        user_prompt: str,
        images: Sequence[str | Path],
    ) -> ProviderResponse:
        """Run one strict response request, copying image inputs into isolation."""

        source_images = [Path(image) for image in images]
        for image in source_images:
            if not image.is_file():
                raise ProviderError(f"Codex image input was not found: {image}")

        started = monotonic()
        prompt = _prompt_without_embedded_schema(system_prompt, user_prompt)
        with TemporaryDirectory(prefix="visiogen-codex-") as directory:
            workdir = Path(directory)
            schema_path = workdir / "output-schema.json"
            output_path = workdir / "response.json"
            schema_path.write_text(
                json.dumps(_strict_output_schema(self._output_model), indent=2) + "\n"
            )

            copied_images: list[Path] = []
            for index, image in enumerate(source_images):
                destination = workdir / image.name
                if destination.exists():
                    destination = workdir / f"{index}-{image.name}"
                shutil.copy2(image, destination)
                copied_images.append(destination)

            command = [
                self._settings.codex_command,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--config",
                'shell_environment_policy.inherit="none"',
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
            ]
            if copied_images:
                command.extend(["--image", *(str(image) for image in copied_images)])
            command.append("-")

            try:
                completed = self._runner(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self._settings.timeout_seconds,
                    cwd=workdir,
                    env=_subprocess_environment(),
                )
            except FileNotFoundError as error:
                raise ProviderError("Codex CLI executable was not found") from error
            except subprocess.TimeoutExpired as error:
                raise ProviderError("Codex CLI request timed out") from error
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
            transport_prompt=prompt,
        )


class CodexCLIExtractor:
    """Extract canonical semantics through an isolated local Codex CLI process."""

    def __init__(
        self,
        settings: Settings,
        *,
        runner: ProcessRunner | None = None,
    ) -> None:
        self._caller = CodexStructuredCaller(
            settings,
            ExtractedDiagramGraph,
            runner=runner,
        )
        self._workflow = StructuredExtractionWorkflow(self._caller)

    def extract(self, text: str) -> DiagramGraph:
        return self._workflow.extract(text)
