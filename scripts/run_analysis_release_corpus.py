#!/usr/bin/env python3
"""Run an immutable A8 PDF/DOCX corpus through the production analysis pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from visiogen.analysis.release_evaluation import ReleaseCase, validate_release_corpus
from visiogen.analysis.release_execution import ExecutedCase, verify_analysis_bundle
from visiogen.analysis.production import build_codex_analysis_pipeline
from visiogen.config import Settings
from visiogen.documents.artifacts import publish_artifact_directory

_REPOSITORY = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=_REPOSITORY,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--case", action="append", dest="case_ids")
    args = parser.parse_args()
    corpus_path = args.corpus.resolve()
    output = args.output.resolve()
    if output == _REPOSITORY or _REPOSITORY in output.parents:
        parser.error("A8 output must be outside the source checkout")
    if _git("status", "--porcelain"):
        parser.error("A8 execution requires a clean immutable source checkout")
    corpus_raw = json.loads(corpus_path.read_text())
    all_cases = [ReleaseCase.model_validate(item) for item in corpus_raw["cases"]]
    validation = validate_release_corpus(all_cases, corpus_path.parent)
    if not validation.valid:
        parser.error("Invalid A8 corpus: " + "; ".join(validation.failures))
    requested = set(args.case_ids or [])
    cases = [case for case in all_cases if not requested or case.id in requested]
    unknown = requested - {case.id for case in cases}
    if unknown:
        parser.error("Unknown corpus cases: " + ", ".join(sorted(unknown)))
    settings = Settings(
        provider="codex",
        codex_model=args.model,
        timeout_seconds=args.timeout,
    )
    source_revision = _git("rev-parse", "HEAD")

    def build(stage: Path) -> dict[str, object]:
        outcomes: list[ExecutedCase] = []
        for case in cases:
            case_root = stage / "cases" / case.id
            bundle = case_root / "bundle"
            source = corpus_path.parent / case.source_path
            try:
                pipeline = build_codex_analysis_pipeline(settings)
                pipeline.analyze(source, bundle)
                outcome = verify_analysis_bundle(case, bundle)
            except Exception as error:
                outcome = ExecutedCase(
                    case_id=case.id,
                    status="failed",
                    source_sha256=case.source_sha256,
                    failures=[f"{type(error).__name__}: {error}"],
                )
            (case_root / "execution.json").parent.mkdir(parents=True, exist_ok=True)
            (case_root / "execution.json").write_text(
                json.dumps(outcome.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
            )
            outcomes.append(outcome)
        complete_corpus = not requested and len(cases) == len(all_cases)
        passed = complete_corpus and all(item.status == "complete" for item in outcomes)
        report: dict[str, object] = {
            "status": "passed" if passed else ("exploratory" if not complete_corpus else "failed"),
            "source_revision": source_revision,
            "source_clean": True,
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "provider": "codex-cli",
            "model": args.model,
            "complete_corpus": complete_corpus,
            "corpus_validation": validation.model_dump(mode="json"),
            "cases": [item.model_dump(mode="json") for item in outcomes],
        }
        (stage / "execution-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        return report

    report = publish_artifact_directory(output, build)
    print(f"A8 corpus execution: {report['status']}")
    print(f"Evidence: {output}")
    return 0 if report["status"] in {"passed", "exploratory"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
