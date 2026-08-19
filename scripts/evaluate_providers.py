#!/usr/bin/env python3
"""Run the opt-in live extraction fixture evaluation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from visiogen.config import Settings
from visiogen.provider_evaluation import evaluate_fixture_corpus
from visiogen.provider_factory import create_extractor, selected_model


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Evaluate one live extraction provider against reviewed fixtures."
    )
    parser.add_argument(
        "--provider", required=True, choices=("codex", "local", "gemini")
    )
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=project_root / "tests" / "fixtures",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=project_root / "artifacts" / "provider-evaluation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    environ = dict(os.environ)
    environ["VISIOGEN_PROVIDER"] = args.provider
    settings = Settings.from_env(environ)
    extractor = create_extractor(settings)
    report = evaluate_fixture_corpus(
        extractor,
        provider=args.provider,
        model=selected_model(settings),
        fixtures_root=args.fixtures_root,
        artifact_root=args.artifact_root,
    )
    report_path = (
        args.artifact_root / args.provider / "semantic-mismatch-report.json"
    )
    print(
        f"{args.provider}: {report['case_count']} cases, "
        f"{report['mismatch_count']} mismatches; report: {report_path}"
    )
    return 0 if report["mismatch_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
