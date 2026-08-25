#!/usr/bin/env python3
"""Run the reviewed deterministic A6 consistency corpus through production rules."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from visiogen.analysis.comparison import compare_diagram_and_claims
from visiogen.analysis.comparison_evaluation import (
    aggregate_consistency_scores,
    score_consistency_case,
)

_REPOSITORY = Path(__file__).resolve().parents[1]
_CORPUS = _REPOSITORY / "tests/fixtures/analysis/consistency_corpus.json"
_BUILDERS = _REPOSITORY / "tests/analysis"
_IMPLEMENTATION_FILES = (
    _REPOSITORY / "src/visiogen/analysis/comparison.py",
    _REPOSITORY / "src/visiogen/analysis/adjudication.py",
    _REPOSITORY / "src/visiogen/analysis/comparison_evaluation.py",
    _BUILDERS / "consistency_fixture_builders.py",
)
_THRESHOLDS = {
    "case_accuracy": 1.0,
    "confirmed_contradiction_precision": 0.90,
    "evidence_validity": 1.0,
    "ambiguous_safety": 1.0,
    "non_exhaustive_omission_false_positives": 0,
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_REPOSITORY, text=True, capture_output=True, check=True
    ).stdout.strip()


def _implementation_sha256() -> str:
    digest = hashlib.sha256()
    for path in _IMPLEMENTATION_FILES:
        digest.update(path.relative_to(_REPOSITORY).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", dest="case_ids")
    args = parser.parse_args()
    corpus_bytes = _CORPUS.read_bytes()
    corpus = json.loads(corpus_bytes)
    requested = set(args.case_ids or [])
    cases = [case for case in corpus["cases"] if not requested or case["id"] in requested]
    complete = len(cases) == len(corpus["cases"])
    sys.path.insert(0, str(_BUILDERS))
    from consistency_fixture_builders import build_consistency_case

    scores = []
    records = []
    failures = []
    for case in cases:
        try:
            diagram, batch, alignments = build_consistency_case(case)
            analysis = compare_diagram_and_claims(
                diagram,
                batch,
                alignments,
                strict_coverage=case["exhaustive_scope"],
            )
            score = score_consistency_case(
                case["id"],
                case["expected_category"],
                case["expected_status"],
                analysis,
                exhaustive_scope=case["exhaustive_scope"],
            )
            scores.append(score)
            records.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "variant": case["variant"],
                    "expected_category": case["expected_category"],
                    "expected_status": case["expected_status"],
                    "diagram": diagram.model_dump(mode="json"),
                    "claims": batch.model_dump(mode="json"),
                    "alignments": alignments.model_dump(mode="json"),
                    "analysis": analysis.model_dump(mode="json"),
                    "score": score.model_dump(mode="json"),
                }
            )
        except Exception as error:
            failure = {"id": case["id"], "error": f"{type(error).__name__}: {error}"}
            failures.append(failure)
            records.append({"id": case["id"], "failure": failure})

    aggregate = aggregate_consistency_scores(scores)
    ambiguous = [
        record
        for record in records
        if record.get("variant") == "ambiguous" and "analysis" in record
    ]
    ambiguous_safe = sum(
        all(
            finding["status"]
            not in {"confirmed_contradiction", "probable_contradiction"}
            for finding in record["analysis"]["findings"]
        )
        for record in ambiguous
    )
    metrics = {
        "case_accuracy": aggregate.case_accuracy,
        "confirmed_contradiction_precision": aggregate.confirmed_contradiction_precision,
        "evidence_validity": aggregate.evidence_validity,
        "ambiguous_safety": ambiguous_safe / len(ambiguous) if ambiguous else 1.0,
        "non_exhaustive_omission_false_positives": (
            aggregate.non_exhaustive_omission_false_positives
        ),
    }
    passed = (
        complete
        and not failures
        and metrics["case_accuracy"] >= _THRESHOLDS["case_accuracy"]
        and metrics["confirmed_contradiction_precision"]
        >= _THRESHOLDS["confirmed_contradiction_precision"]
        and metrics["evidence_validity"] >= _THRESHOLDS["evidence_validity"]
        and metrics["ambiguous_safety"] >= _THRESHOLDS["ambiguous_safety"]
        and metrics["non_exhaustive_omission_false_positives"]
        <= _THRESHOLDS["non_exhaustive_omission_false_positives"]
    )
    report = {
        "status": "passed" if passed else ("exploratory" if not complete else "failed"),
        "source_revision": _git("rev-parse", "HEAD"),
        "source_state": "content-addressed implementation and corpus",
        "implementation_sha256": _implementation_sha256(),
        "provider": "none-deterministic",
        "model_calls": 0,
        "corpus_version": corpus["version"],
        "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
        "complete_corpus": complete,
        "case_count": len(cases),
        "thresholds": _THRESHOLDS,
        "metrics": metrics,
        "failures": failures,
        "cases": records,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"A6 consistency acceptance: {report['status']}")
    print(f"Evidence: {output}")
    return 0 if report["status"] in {"passed", "exploratory"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
