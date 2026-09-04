"""Generation v2 vertical pipeline from specification to native VSDX."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from visiogen.config import Settings
from visiogen.generation.compiler import RendererIR, compile_construction_plan
from visiogen.generation.planner import (
    ConstructionPlanResult,
    StructuredConstructionPlanner,
    build_construction_prompt,
)
from visiogen.generation.specification import DiagramSpecification
from visiogen.generation.specification_workflow import (
    SpecificationResult,
    StructuredSpecificationWorkflow,
    build_specification_prompt,
)
from visiogen.pipeline import (
    GenerationResult,
    _atomic_copy,
    _persist_raw_response,
    _prepare_paths,
    _schema_sha256,
    _sha256,
    _sha256_bytes,
    _source_state,
    _write_json,
    _write_text,
)
from visiogen.renderer import render_ir
from visiogen.validation import validate_vsdx_package


class DiagramSpecifier(Protocol):
    def specify(self, text: str) -> SpecificationResult: ...


class ConstructionPlanner(Protocol):
    def plan(self, specification: DiagramSpecification) -> ConstructionPlanResult: ...


RenderCall = Callable[[str | Path, RendererIR, str | Path], Path]
ValidatePackageCall = Callable[[str | Path], None]
ProgressReporter = Callable[["GenerationProgress"], None]


@dataclass(frozen=True, slots=True)
class GenerationProgress:
    stage: str
    message: str


class GenerationV2Pipeline:
    """Specify, plan, compile, render, and publish one auditable V2 result."""

    def __init__(
        self,
        *,
        specifier: DiagramSpecifier,
        planner: ConstructionPlanner,
        template_path: str | Path,
        provider: str,
        model: str,
        render: RenderCall = render_ir,
        validate_package: ValidatePackageCall = validate_vsdx_package,
    ) -> None:
        self._specifier = specifier
        self._planner = planner
        self._template_path = Path(template_path)
        self._provider = provider
        self._model = model
        self._render = render
        self._validate_package = validate_package

    def generate(
        self,
        source: str | DiagramSpecification,
        output_path: str | Path,
        *,
        artifact_dir: str | Path,
        progress: ProgressReporter | None = None,
    ) -> GenerationResult:
        def report(stage: str, message: str) -> None:
            if progress is not None:
                progress(GenerationProgress(stage=stage, message=message))

        destination = Path(output_path)
        artifacts = Path(artifact_dir)
        report("prepare", "Preparing output and evidence paths")
        _prepare_paths(destination, artifacts)

        specification_result: SpecificationResult | None = None
        if isinstance(source, DiagramSpecification):
            specification = source
            original_request = None
        else:
            original_request = source
            _write_text(artifacts / "01-request.txt", source)
            _write_text(
                artifacts / "02-specification-system-prompt.txt",
                build_specification_prompt(),
            )
            report(
                "specification",
                "Creating and validating the diagram specification (model call)",
            )
            specification_result = self._specifier.specify(source)
            specification = specification_result.specification
            self._persist_model_trace(
                artifacts,
                "03-specification",
                specification_result.user_prompts,
                specification_result.raw_responses,
                specification_result.transport_prompts,
            )
            report(
                "specification_complete",
                f"Specification validated in {specification_result.attempts} attempt(s)",
            )

        specification_path = artifacts / "04-validated-specification.json"
        _write_json(specification_path, specification.model_dump(mode="json"))

        _write_text(
            artifacts / "05-construction-system-prompt.txt",
            build_construction_prompt(),
        )
        report(
            "construction",
            "Planning exact Visio shapes, geometry, and connector routes (model call)",
        )
        plan_result = self._planner.plan(specification)
        self._persist_model_trace(
            artifacts,
            "06-construction",
            plan_result.user_prompts,
            plan_result.raw_responses,
            plan_result.transport_prompts,
        )
        report(
            "construction_complete",
            f"Construction plan validated in {plan_result.attempts} attempt(s)",
        )
        plan_path = artifacts / "07-validated-construction-plan.json"
        _write_json(plan_path, plan_result.plan.model_dump(mode="json"))

        report("compile", "Compiling the construction plan into renderer IR")
        renderer_ir = compile_construction_plan(specification, plan_result.plan)
        ir_path = artifacts / "08-renderer-ir.json"
        _write_json(ir_path, renderer_ir.model_dump(mode="json"))

        report("render", "Rendering the editable native VSDX")
        rendered = Path(self._render(self._template_path, renderer_ir, destination))
        if rendered.resolve() != destination.resolve():
            raise RuntimeError("Renderer returned an unexpected output path")
        if destination.is_symlink() or not destination.is_file():
            raise RuntimeError("Renderer did not produce a regular output file")
        destination.chmod(0o600)
        report("validate", "Validating the generated VSDX package")
        self._validate_package(destination)
        retained_vsdx = artifacts / "09-final.vsdx"
        if destination.resolve() != retained_vsdx.resolve():
            _atomic_copy(destination, retained_vsdx)

        report("publish", "Writing checksums and the provenance manifest")
        artifact_sha256 = {
            str(path.relative_to(artifacts)): _sha256(path)
            for path in sorted(artifacts.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }
        manifest = {
            "architecture": "ai-directed-native-visio-v2",
            **_source_state(),
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "provider": self._provider,
            "model": self._model,
            "output": destination.name,
            "output_sha256": _sha256(destination),
            "request_sha256": (
                _sha256_bytes(original_request.encode())
                if original_request is not None
                else None
            ),
            "template": str(self._template_path),
            "template_sha256": _sha256(self._template_path),
            "diagram_specification_version": specification.version,
            "diagram_specification_sha256": _sha256(specification_path),
            "diagram_specification_schema_sha256": _schema_sha256(
                DiagramSpecification
            ),
            "specification_attempts": (
                specification_result.attempts if specification_result else 0
            ),
            "specification_request_ids": (
                list(specification_result.request_ids) if specification_result else []
            ),
            "specification_elapsed_ms": (
                specification_result.elapsed_ms if specification_result else 0.0
            ),
            "construction_plan_version": plan_result.plan.version,
            "construction_plan_sha256": _sha256(plan_path),
            "construction_plan_schema_sha256": _schema_sha256(type(plan_result.plan)),
            "construction_prompt_version": plan_result.prompt_version,
            "construction_examples_version": plan_result.examples_version,
            "construction_attempts": plan_result.attempts,
            "construction_request_ids": list(plan_result.request_ids),
            "construction_elapsed_ms": plan_result.elapsed_ms,
            "renderer_ir_version": renderer_ir.version,
            "renderer_ir_sha256": _sha256(ir_path),
            "renderer_ir_schema_sha256": _schema_sha256(RendererIR),
            "artifact_sha256": artifact_sha256,
            "visual_diagnostics_performed": False,
            "visual_editing_performed": False,
            "windows_visio_acceptance": "pending",
        }
        _write_json(artifacts / "manifest.json", manifest)
        report("complete", "Generation complete")
        return GenerationResult(
            output_path=destination,
            artifact_dir=artifacts,
            provider=self._provider,
            model=self._model,
        )

    @staticmethod
    def _persist_model_trace(
        artifacts: Path,
        prefix: str,
        prompts: tuple[str, ...],
        responses: tuple[str, ...],
        transport_prompts: tuple[str | None, ...],
    ) -> None:
        for index, prompt in enumerate(prompts, start=1):
            _write_text(artifacts / f"{prefix}-user-prompt-{index}.txt", prompt)
        for index, response in enumerate(responses, start=1):
            _persist_raw_response(artifacts / f"{prefix}-response-{index}", response)
        for index, prompt in enumerate(transport_prompts, start=1):
            if prompt is not None:
                _write_text(
                    artifacts / f"{prefix}-provider-prompt-{index}.txt", prompt
                )


def build_codex_generation_v2_pipeline(
    settings: Settings,
    template_path: str | Path,
    *,
    enable_critique: bool = True,
) -> GenerationV2Pipeline:
    """Build the production V2 pipeline; later visual stages remain explicit."""

    del enable_critique
    from visiogen.generation.construction import VisioConstructionPlan
    from visiogen.providers.codex_cli import CodexStructuredCaller

    return GenerationV2Pipeline(
        specifier=StructuredSpecificationWorkflow(
            CodexStructuredCaller(settings, DiagramSpecification)
        ),
        planner=StructuredConstructionPlanner(
            CodexStructuredCaller(settings, VisioConstructionPlan)
        ),
        template_path=template_path,
        provider=settings.provider,
        model=settings.codex_model,
    )
