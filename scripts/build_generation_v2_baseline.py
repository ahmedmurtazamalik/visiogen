#!/usr/bin/env python3
"""Validate the frozen Generation v2 corpus and create an honest V1 baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from visiogen.generation.evaluation import (
    BaselineCaseResult,
    BaselineReport,
    GenerationCorpus,
    sha256_bytes,
    validate_baseline_report,
    validate_generation_corpus,
)


CURRENT_LIMITATIONS = [
    "No current checksum-bound Windows Generation v1 corpus exists for these frozen cases.",
    "The available hybrid generation bundle skipped visual critique and has no final preview.",
    "The superseded M6 R2 previews contain visible connector and label defects and are not a current baseline.",
    "Generation connector-side hints reach LayoutResult but are not consumed by the renderer.",
    "A critique-driven revised preview is not submitted for final visual re-approval.",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--generation-test-count", type=int, required=True)
    args = parser.parse_args()

    corpus_bytes = args.corpus.read_bytes()
    corpus = GenerationCorpus.model_validate_json(corpus_bytes)
    validation = validate_generation_corpus(corpus)
    if not validation.valid:
        for failure in validation.failures:
            print(f"Corpus failure: {failure}")
        return 1

    reason = (
        "Not run: G0 was prepared on Linux and visual/native evidence requires "
        "desktop Microsoft Visio on Windows. This is unavailable evidence, not a pass."
    )
    report = BaselineReport(
        status="incomplete",
        source_revision=args.source_revision,
        corpus_sha256=sha256_bytes(corpus_bytes),
        generation_test_count=args.generation_test_count,
        generation_tests_passed=True,
        current_limitations=CURRENT_LIMITATIONS,
        cases=[
            BaselineCaseResult(
                case_id=case.id,
                evidence_state="unavailable",
                reason=reason,
            )
            for case in corpus.cases
        ],
    )
    binding_failures = validate_baseline_report(corpus, report)
    if binding_failures:
        for failure in binding_failures:
            print(f"Baseline failure: {failure}")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Generation v1 baseline: incomplete (Windows visual evidence unavailable)")
    print(f"Corpus cases: {validation.case_count}")
    print(f"Report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
