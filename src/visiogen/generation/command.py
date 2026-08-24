"""Text-to-VSDX command owned by the generation workstream."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from visiogen.config import Settings
from visiogen.pipeline import HybridGenerationPipeline

PipelineFactory = Callable[..., HybridGenerationPipeline]
_DEFAULT_TEMPLATE = Path(__file__).resolve().parents[3] / "templates" / "template.vsdx"


def register_generate_command(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    pipeline_factory: PipelineFactory,
) -> None:
    """Register generation arguments without exposing them to other workstreams."""

    generate = commands.add_parser(
        "generate",
        help="Design, render, preview, and visually critique a VSDX",
    )
    source = generate.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Natural-language diagram request")
    source.add_argument("--input-file", type=Path, help="UTF-8 request text file")
    generate.add_argument("--output", type=Path, required=True, help="Final .vsdx path")
    generate.add_argument(
        "--artifact-dir",
        type=Path,
        required=True,
        help="Visible directory for prompts, responses, previews, and provenance",
    )
    generate.add_argument(
        "--template",
        type=Path,
        default=_DEFAULT_TEMPLATE,
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
        help="Skip image critique explicitly (recorded in the manifest)",
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
    """Run the existing hybrid generation pipeline."""

    if not args.template.is_file():
        raise argparse.ArgumentError(None, f"Template file was not found: {args.template}")
    if args.text is not None:
        text = args.text
    else:
        try:
            text = args.input_file.read_text()
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
        result = pipeline.generate(
            text,
            args.output,
            artifact_dir=args.artifact_dir,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise argparse.ArgumentError(None, f"Generation failed: {error}") from error
    print(f"VSDX: {result.output_path}")
    print(f"Evidence: {result.artifact_dir}")
    return 0
