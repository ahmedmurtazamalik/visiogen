"""Text-to-VSDX command owned by the generation workstream."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from time import monotonic
from typing import Protocol

from visiogen.config import Settings
from visiogen.generation.analysis_import import (
    AnalysisImportError,
    import_analysis_bundle,
    write_specification,
)
from visiogen.generation.pipeline import GenerationProgress
from visiogen.generation.specification import (
    DiagramSpecification,
    SpecificationError,
    load_specification,
)
from visiogen.pipeline import GenerationResult


class GenerationPipeline(Protocol):
    def generate(
        self,
        source: str | DiagramSpecification,
        output_path: str | Path,
        *,
        artifact_dir: str | Path,
        progress: Callable[[GenerationProgress], None] | None = None,
    ) -> GenerationResult: ...


PipelineFactory = Callable[..., GenerationPipeline]


def _default_template_path() -> Path:
    packaged = Path(str(files("visiogen").joinpath("templates", "template.vsdx")))
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[3] / "templates" / "template.vsdx"


def register_generate_command(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    pipeline_factory: PipelineFactory,
) -> None:
    """Register generation arguments without exposing them to other workstreams."""

    generate = commands.add_parser(
        "generate",
        help="Plan, compile, and render an editable native VSDX",
    )
    source = generate.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Natural-language diagram request")
    source.add_argument("--input-file", type=Path, help="UTF-8 request text file")
    source.add_argument(
        "--spec-file",
        type=Path,
        help="Validated DiagramSpecification in JSON or YAML",
    )
    source.add_argument(
        "--analysis-bundle",
        type=Path,
        help="Completed analysis evidence bundle to project into a draft specification",
    )
    generate.add_argument(
        "--analysis-candidate",
        help="Candidate ID when an analysis bundle contains multiple completed diagrams",
    )
    generate.add_argument(
        "--stop-after-specification",
        action="store_true",
        help="Write the projected analysis specification to --output and stop",
    )
    generate.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Final .vsdx path, or draft .json path when stopping after specification",
    )
    generate.add_argument(
        "--artifact-dir",
        type=Path,
        required=False,
        help="Visible directory for prompts, plans, compiler IR, and provenance",
    )
    generate.add_argument(
        "--template",
        type=Path,
        default=_default_template_path(),
        help="Canonical native Visio template",
    )
    generate.add_argument("--model", default="gpt-5.6-sol", help="Codex model")
    generate.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Seconds per model call",
    )
    generate.add_argument(
        "--no-critique",
        action="store_true",
        help="Compatibility flag; Generation v2 visual editing is not enabled yet",
    )
    generate.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress updates (final output is still printed)",
    )
    generate.set_defaults(
        command_handler=lambda args: _run_generate(
            args,
            pipeline_factory=pipeline_factory,
        )
    )


def _run_generate(
    args: argparse.Namespace,
    *,
    pipeline_factory: PipelineFactory,
) -> int:
    """Run the configured generation pipeline."""

    if args.stop_after_specification and args.analysis_bundle is None:
        raise argparse.ArgumentError(
            None, "--stop-after-specification requires --analysis-bundle"
        )
    if args.analysis_candidate is not None and args.analysis_bundle is None:
        raise argparse.ArgumentError(None, "--analysis-candidate requires --analysis-bundle")
    if not args.stop_after_specification and args.artifact_dir is None:
        raise argparse.ArgumentError(
            None, "--artifact-dir is required unless stopping after specification"
        )
    if not args.stop_after_specification and not args.template.is_file():
        raise argparse.ArgumentError(None, f"Template file was not found: {args.template}")
    if args.analysis_bundle is not None:
        try:
            source = import_analysis_bundle(
                args.analysis_bundle,
                candidate_id=args.analysis_candidate,
            )
        except AnalysisImportError as error:
            raise argparse.ArgumentError(None, str(error)) from error
        if args.stop_after_specification:
            try:
                output = write_specification(args.output, source)
            except AnalysisImportError as error:
                raise argparse.ArgumentError(None, str(error)) from error
            print(f"Specification: {output}")
            return 0
    elif args.spec_file is not None:
        try:
            source = load_specification(args.spec_file)
        except SpecificationError as error:
            raise argparse.ArgumentError(None, str(error)) from error
    elif args.text is not None:
        source = args.text
    else:
        try:
            source = args.input_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise argparse.ArgumentError(None, f"Could not read input file: {error}") from error
    settings = Settings(
        provider="codex",
        codex_model=args.model,
        timeout_seconds=args.timeout,
    )
    pipeline = pipeline_factory(
        settings,
        args.template,
        enable_critique=not args.no_critique,
    )
    try:
        progress_started = monotonic()

        def show_progress(event: GenerationProgress) -> None:
            elapsed_seconds = int(monotonic() - progress_started)
            elapsed = f"{elapsed_seconds // 60:02d}:{elapsed_seconds % 60:02d}"
            print(
                f"[visiogen {elapsed}] {event.message}",
                file=sys.stderr,
                flush=True,
            )

        result = pipeline.generate(
            source,
            args.output,
            artifact_dir=args.artifact_dir,
            progress=None if args.quiet else show_progress,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise argparse.ArgumentError(None, f"Generation failed: {error}") from error
    print(f"VSDX: {result.output_path}")
    print(f"Evidence: {result.artifact_dir}")
    return 0
