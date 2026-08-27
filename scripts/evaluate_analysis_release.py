#!/usr/bin/env python3
"""Score checksum-bound A8 corpus reviews and publish a release decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from visiogen.analysis.release_evaluation import (
    CaseReview,
    ReleaseCase,
    ReleaseThresholds,
    evaluate_release,
    validate_release_corpus,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus_raw = json.loads(args.corpus.read_text())
    reviews_raw = json.loads(args.reviews.read_text())
    cases = [ReleaseCase.model_validate(item) for item in corpus_raw["cases"]]
    reviews = [CaseReview.model_validate(item) for item in reviews_raw["reviews"]]
    thresholds = ReleaseThresholds.model_validate(
        corpus_raw.get("thresholds", {})
    )
    corpus_validation = validate_release_corpus(cases, args.corpus.resolve().parent)
    decision = evaluate_release(cases, reviews, thresholds)
    if not corpus_validation.valid:
        decision = decision.model_copy(
            update={
                "status": "failed",
                "failures": decision.failures + corpus_validation.failures,
            }
        )
    report = {
        "corpus_sha256": _sha256(args.corpus),
        "reviews_sha256": _sha256(args.reviews),
        "corpus_validation": corpus_validation.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"A8 analysis release decision: {decision.status}")
    print(f"Report: {args.output.resolve()}")
    return 0 if decision.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
