"""Hybrid AI text-to-Visio generation pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from visiogen.config import Settings
from visiogen.critic import CritiqueResult, VisualCritique, build_critique_prompt
from visiogen.design import DiagramDesign
from visiogen.designer import DesignResult, build_design_prompt
from visiogen.layout import LayoutResult
from visiogen.preview import export_vsdx_preview
from visiogen.renderer import render_layout
from visiogen.validation import validate_vsdx_package


class DiagramDesigner(Protocol):
    """Provider-neutral design capability used by the public pipeline."""

    def design(self, text: str) -> DesignResult: ...


class VisualCritic(Protocol):
    """Image-grounded review capability used for one bounded revision."""

    def critique(
        self,
        source_text: str,
        design: DiagramDesign,
        preview_path: str | Path,
    ) -> CritiqueResult: ...


class PipelineError(RuntimeError):
    """Raised before generation when output/evidence paths are unsafe."""


RenderCall = Callable[[str | Path, LayoutResult, str | Path], Path]
ValidatePackageCall = Callable[[str | Path], None]
PreviewCall = Callable[[str | Path, str | Path], Path]


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Paths and model provenance for a completed hybrid generation."""

    output_path: Path
    artifact_dir: Path
    provider: str
    model: str


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        output_file = os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            newline="",
        )
        descriptor = -1
        with output_file:
            output_file.write(content)
        temporary.chmod(0o600)
        temporary.replace(path)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def _write_json(path: Path, value: object) -> None:
    _write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _schema_sha256(model_type: type[object]) -> str:
    schema = model_type.model_json_schema()  # type: ignore[attr-defined]
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    return _sha256_bytes(encoded)


def _source_state() -> dict[str, object]:
    """Record identity only when this module belongs to a Git source checkout."""

    source_file = Path(__file__).resolve()
    repository = source_file.parents[2]
    checkout_module = repository / "src" / "visiogen" / "pipeline.py"
    if not (repository / ".git").exists() or checkout_module.resolve() != source_file:
        return {"source_revision": None, "source_worktree_clean": None}
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=repository,
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
        ).stdout
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return {"source_revision": None, "source_worktree_clean": None}
    return {
        "source_revision": revision or None,
        "source_worktree_clean": not bool(status.strip()),
    }


def _persist_raw_response(path_without_suffix: Path, response: str) -> None:
    try:
        json.loads(response)
    except json.JSONDecodeError:
        _write_text(path_without_suffix.with_suffix(".txt"), response)
    else:
        _write_text(path_without_suffix.with_suffix(".json"), response)


def _atomic_copy(source: Path, destination: Path) -> None:
    """Copy bytes through a fresh sibling and atomically replace the destination."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        output_file = os.fdopen(descriptor, "wb")
        descriptor = -1
        with source.open("rb") as input_file, output_file:
            shutil.copyfileobj(input_file, output_file)
        temporary.chmod(0o600)
        temporary.replace(destination)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def _prepare_paths(output: Path, artifacts: Path) -> None:
    """Create a private empty evidence directory and reject collisions."""

    if artifacts.is_symlink():
        raise PipelineError("Evidence directory must not be a symbolic link")
    if artifacts.exists():
        if not artifacts.is_dir():
            raise PipelineError("Evidence path must be a directory")
        if any(artifacts.iterdir()):
            raise PipelineError("Evidence directory must be empty")
    else:
        artifacts.mkdir(parents=True, mode=0o700)
    artifacts.chmod(0o700)

    if output.is_symlink():
        raise PipelineError("Output path must not be a symbolic link")
    output.parent.mkdir(parents=True, exist_ok=True)
    reserved_prefixes = tuple(f"{index:02d}-" for index in range(100))
    if output.parent.resolve() == artifacts.resolve() and (
        output.name in {"manifest.json", "manifest.json.tmp"}
        or output.name.startswith(reserved_prefixes)
    ):
        raise PipelineError("Output uses a reserved evidence filename")


class HybridGenerationPipeline:
    """Compose AI design, hard checks, native rendering, and one image revision."""

    def __init__(
        self,
        *,
        designer: DiagramDesigner,
        template_path: str | Path,
        provider: str,
        model: str,
        render: RenderCall = render_layout,
        validate_package: ValidatePackageCall = validate_vsdx_package,
        critic: VisualCritic | None = None,
        export_preview: PreviewCall = export_vsdx_preview,
    ) -> None:
        self._designer = designer
        self._template_path = Path(template_path)
        self._provider = provider
        self._model = model
        self._render = render
        self._validate_package = validate_package
        self._critic = critic
        self._export_preview = export_preview

    def generate(
        self,
        text: str,
        output_path: str | Path,
        *,
        artifact_dir: str | Path,
    ) -> GenerationResult:
        """Generate and optionally critique one native VSDX with full provenance."""

        destination = Path(output_path)
        artifacts = Path(artifact_dir)
        _prepare_paths(destination, artifacts)

        _write_text(artifacts / "00-design-system-prompt.txt", build_design_prompt())
        _write_text(artifacts / "01-request.txt", text)

        result = self._designer.design(text)
        for index, prompt in enumerate(result.user_prompts, start=1):
            _write_text(
                artifacts / f"01-design-user-prompt-{index}.txt",
                prompt,
            )
        for index, response in enumerate(result.raw_responses, start=1):
            _persist_raw_response(
                artifacts / f"02-design-response-{index}",
                response,
            )
        for index, transport_prompt in enumerate(result.transport_prompts, start=1):
            if transport_prompt is not None:
                _write_text(
                    artifacts / f"02-provider-prompt-{index}.txt",
                    transport_prompt,
                )

        design = result.design
        _write_json(
            artifacts / "03-validated-design.json",
            design.model_dump(mode="json"),
        )
        layout = design.to_layout_result()
        _write_json(
            artifacts / "04-layout.json",
            {
                "page": layout.page.model_dump(mode="json"),
                "graph": layout.graph.model_dump(mode="json"),
                "composition": design.layout.composition,
                "connector_hints": [
                    hint.model_dump(mode="json")
                    for hint in design.layout.connector_hints
                ],
            },
        )

        rendered = Path(self._render(self._template_path, layout, destination))
        if rendered.resolve() != destination.resolve():
            raise PipelineError("Renderer returned an unexpected output path")
        if destination.is_symlink() or not destination.is_file():
            raise PipelineError("Renderer did not produce a regular output file")
        output = destination
        output.chmod(0o600)
        self._validate_package(output)

        initial_artifact = artifacts / "05-initial.vsdx"
        if output.resolve() != initial_artifact.resolve():
            _atomic_copy(output, initial_artifact)
        initial_artifact.chmod(0o600)

        visual_performed = False
        initial_approved: bool | None = None
        revision_applied = False
        critique_elapsed_ms = 0.0

        if self._critic is not None:
            visual_performed = True
            initial_preview = self._export_preview(
                initial_artifact,
                artifacts / "06-initial-preview.png",
            )
            Path(initial_preview).chmod(0o600)
            _write_text(
                artifacts / "07-critique-system-prompt.txt",
                build_critique_prompt(),
            )
            critique_result = self._critic.critique(text, design, initial_preview)
            _write_text(
                artifacts / "07-critique-user-prompt.txt",
                critique_result.user_prompt,
            )
            if critique_result.transport_prompt is not None:
                _write_text(
                    artifacts / "07-critique-provider-prompt.txt",
                    critique_result.transport_prompt,
                )
            critique_elapsed_ms = critique_result.elapsed_ms
            initial_approved = critique_result.critique.approved
            _persist_raw_response(
                artifacts / "08-critique-response",
                critique_result.raw_response,
            )

            if critique_result.revised_design is not None:
                revision_applied = True
                revised_design = critique_result.revised_design
                _write_json(
                    artifacts / "09-revised-design.json",
                    revised_design.model_dump(mode="json"),
                )
                revised_artifact = artifacts / "10-revised.vsdx"
                self._render(
                    self._template_path,
                    revised_design.to_layout_result(),
                    revised_artifact,
                )
                self._validate_package(revised_artifact)
                revised_artifact.chmod(0o600)
                _atomic_copy(revised_artifact, destination)
                destination.chmod(0o600)
                output = destination
                final_preview = self._export_preview(
                    revised_artifact,
                    artifacts / "11-final-preview.png",
                )
                Path(final_preview).chmod(0o600)
            else:
                final_preview = artifacts / "11-final-preview.png"
                if Path(initial_preview).resolve() != final_preview.resolve():
                    _atomic_copy(Path(initial_preview), final_preview)
                final_preview.chmod(0o600)

        artifact_sha256 = {
            str(path.relative_to(artifacts)): _sha256(path)
            for path in sorted(artifacts.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }
        final_preview_path = artifacts / "11-final-preview.png"
        manifest = {
            "architecture": "hybrid-ai-v1",
            **_source_state(),
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "provider": self._provider,
            "model": self._model,
            "design_attempts": result.metadata.attempts,
            "request_ids": list(result.metadata.request_ids),
            "design_elapsed_ms": result.metadata.elapsed_ms,
            "output": output.name,
            "output_sha256": _sha256(output),
            "request_sha256": _sha256_bytes(text.encode()),
            "template": str(self._template_path),
            "template_sha256": (
                _sha256(self._template_path)
                if self._template_path.is_file()
                else None
            ),
            "diagram_design_schema_sha256": _schema_sha256(DiagramDesign),
            "visual_critique_schema_sha256": _schema_sha256(VisualCritique),
            "initial_vsdx_sha256": _sha256(initial_artifact),
            "final_preview_sha256": (
                _sha256(final_preview_path) if final_preview_path.is_file() else None
            ),
            "artifact_sha256": artifact_sha256,
            "visual_critique_performed": visual_performed,
            "visual_critique_approved_initial": initial_approved,
            "visual_critique_elapsed_ms": critique_elapsed_ms,
            "revision_applied": revision_applied,
        }
        _write_json(artifacts / "manifest.json", manifest)

        return GenerationResult(
            output_path=output,
            artifact_dir=artifacts,
            provider=self._provider,
            model=self._model,
        )


def build_codex_hybrid_pipeline(
    settings: Settings,
    template_path: str | Path,
    *,
    enable_critique: bool = True,
) -> HybridGenerationPipeline:
    """Build the preferred real Codex design and multimodal-critique pipeline."""

    from visiogen.critic import StructuredVisualCritic, VisualCritique
    from visiogen.design import DiagramDesign
    from visiogen.designer import StructuredDesignWorkflow
    from visiogen.providers.codex_cli import CodexStructuredCaller

    designer = StructuredDesignWorkflow(
        CodexStructuredCaller(settings, DiagramDesign)
    )
    critic = (
        StructuredVisualCritic(CodexStructuredCaller(settings, VisualCritique))
        if enable_critique
        else None
    )
    return HybridGenerationPipeline(
        designer=designer,
        critic=critic,
        template_path=template_path,
        provider=settings.provider,
        model=settings.codex_model,
    )
