"""Stable top-level command dispatcher for independent Visiogen workstreams."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from visiogen.analysis.command import AnalysisPipelineFactory, register_analysis_command
from visiogen.analysis.production import build_codex_analysis_pipeline
from visiogen.generation.command import PipelineFactory, register_generate_command
from visiogen.generation.pipeline import build_codex_generation_v2_pipeline


def build_parser(
    *,
    pipeline_factory: PipelineFactory = build_codex_generation_v2_pipeline,
    analysis_pipeline_factory: AnalysisPipelineFactory = build_codex_analysis_pipeline,
) -> argparse.ArgumentParser:
    """Build the public CLI from workstream-owned command registrations."""

    parser = argparse.ArgumentParser(
        prog="visiogen",
        description="Generate Visio diagrams and analyze diagrams in documents.",
    )
    commands = parser.add_subparsers(dest="command")
    register_generate_command(commands, pipeline_factory=pipeline_factory)
    register_analysis_command(commands, pipeline_factory=analysis_pipeline_factory)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    pipeline_factory: PipelineFactory = build_codex_generation_v2_pipeline,
    analysis_pipeline_factory: AnalysisPipelineFactory = build_codex_analysis_pipeline,
) -> int:
    """Parse arguments and invoke the handler owned by the selected workstream."""

    parser = build_parser(
        pipeline_factory=pipeline_factory,
        analysis_pipeline_factory=analysis_pipeline_factory,
    )
    args = parser.parse_args(argv)
    handler = getattr(args, "command_handler", None)
    if handler is None:
        parser.print_help()
        return 0
    try:
        return handler(args)
    except argparse.ArgumentError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
