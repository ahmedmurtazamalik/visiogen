"""CLI registration boundary for the document-analysis workstream."""

from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from visiogen.analysis.pipeline import AnalysisPipelineOptions, DocumentAnalysisPipeline
from visiogen.config import Settings
from visiogen.documents.errors import DocumentError
from visiogen.providers.base import ProviderError

AnalysisPipelineFactory = Callable[[Settings], DocumentAnalysisPipeline]


def register_analysis_command(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    pipeline_factory: AnalysisPipelineFactory,
) -> None:
    """Register the public PDF/DOCX diagram-analysis command."""

    analyze = commands.add_parser(
        "analyze",
        help="Analyze diagrams and related prose in a PDF or DOCX",
    )
    analyze.add_argument("--input", type=Path, required=True, help="Source PDF or DOCX")
    analyze.add_argument("--output", type=Path, required=True, help="Published Markdown report")
    analyze.add_argument(
        "--artifact-dir",
        type=Path,
        required=True,
        help="Private directory for evidence, prompts, responses, and provenance",
    )
    analyze.add_argument("--model", default="gpt-5.6-sol", help="Codex vision model")
    analyze.add_argument("--timeout", type=float, default=300.0, help="Seconds per model call")
    filters = analyze.add_mutually_exclusive_group()
    filters.add_argument("--page", type=int, help="Analyze candidates on one page")
    filters.add_argument("--candidate", help="Analyze one candidate ID")
    analyze.add_argument("--max-diagrams", type=int, default=8)
    analyze.add_argument("--strict-coverage", action="store_true")
    analyze.add_argument(
        "--no-consistency-check",
        action="store_true",
        help="Produce diagram descriptions without comparing document prose",
    )
    analyze.add_argument(
        "--no-semantic-adjudication",
        action="store_true",
        help="Keep deterministic unresolved findings without bounded semantic adjudication",
    )
    analyze.set_defaults(
        command_handler=lambda args: _run_analyze(args, pipeline_factory=pipeline_factory)
    )


def _publish_report(source: Path, destination: Path) -> None:
    if destination.is_symlink() or destination.exists():
        raise ValueError("Report output must be a new, non-symbolic path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(source.read_bytes())
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _run_analyze(
    args: argparse.Namespace,
    *,
    pipeline_factory: AnalysisPipelineFactory,
) -> int:
    if not args.input.is_file():
        raise argparse.ArgumentError(None, f"Input document was not found: {args.input}")
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    artifact_path = args.artifact_dir.resolve()
    if output_path == input_path:
        raise argparse.ArgumentError(None, "Report output must not overwrite the input document")
    if output_path == artifact_path or output_path.is_relative_to(artifact_path):
        raise argparse.ArgumentError(None, "Report output must remain outside the private artifact directory")
    if artifact_path.is_relative_to(output_path):
        raise argparse.ArgumentError(
            None,
            "Private artifact directory must not be nested beneath the report path",
        )
    try:
        options = AnalysisPipelineOptions(
            strict_coverage=args.strict_coverage,
            consistency_check=not args.no_consistency_check,
            page_number=args.page,
            candidate_id=args.candidate,
            max_diagrams=args.max_diagrams,
            semantic_adjudication=not args.no_semantic_adjudication,
        )
        settings = Settings(
            provider="codex",
            codex_model=args.model,
            timeout_seconds=args.timeout,
        )
        pipeline = pipeline_factory(settings)
        result = pipeline.analyze(args.input, args.artifact_dir, options=options)
        _publish_report(result.artifact_dir / "report.md", args.output)
    except (DocumentError, ProviderError, OSError, RuntimeError, ValueError) as error:
        raise argparse.ArgumentError(None, f"Analysis failed: {error}") from error
    print(f"Report: {args.output.resolve()}")
    print(f"Evidence: {result.artifact_dir}")
    if result.analysis.status == "partial":
        print("Status: partial candidate failure")
        return 3
    return 0
