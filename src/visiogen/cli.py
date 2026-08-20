"""Visiogen command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from visiogen.config import Settings
from visiogen.pipeline import HybridGenerationPipeline, build_codex_hybrid_pipeline

PipelineFactory = Callable[..., HybridGenerationPipeline]
_DEFAULT_TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "template.vsdx"


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser and real hybrid generation command."""

    parser = argparse.ArgumentParser(
        prog="visiogen",
        description="Generate editable Visio diagrams with hybrid AI design and critique.",
    )
    commands = parser.add_subparsers(dest="command")
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
    generate.add_argument("--timeout", type=float, default=180.0, help="Seconds per model call")
    generate.add_argument(
        "--no-critique",
        action="store_true",
        help="Skip image critique explicitly (recorded in the manifest)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    pipeline_factory: PipelineFactory = build_codex_hybrid_pipeline,
) -> int:
    """Run the Visiogen command-line interface."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command != "generate":
        parser.error(f"Unsupported command: {args.command}")

    if not args.template.is_file():
        parser.error(f"Template file was not found: {args.template}")
    if args.text is not None:
        text = args.text
    else:
        try:
            text = args.input_file.read_text()
        except (OSError, UnicodeError) as error:
            parser.error(f"Could not read input file: {error}")
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
        parser.error(f"Generation failed: {error}")
    print(f"VSDX: {result.output_path}")
    print(f"Evidence: {result.artifact_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
