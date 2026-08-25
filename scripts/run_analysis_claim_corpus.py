#!/usr/bin/env python3
"""Run the reviewed A5 prose corpus through production claim extraction and alignment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from visiogen.analysis.alignment import align_claim_entities
from visiogen.analysis.claim_workflow import StructuredClaimExtractionWorkflow
from visiogen.analysis.claims import DocumentClaimBatch
from visiogen.config import Settings
from visiogen.documents.artifacts import publish_artifact_directory
from visiogen.providers.codex_cli import CodexStructuredCaller

_REPOSITORY = Path(__file__).resolve().parents[1]
_CORPUS = _REPOSITORY / "tests/fixtures/analysis/claim_corpus.json"
_BUILDERS = _REPOSITORY / "tests/analysis"
_THRESHOLDS = {
    "claim_recall": 0.90,
    "modality_accuracy": 1.0,
    "exact_span_validity": 1.0,
    "alias_alignment": 1.0,
    "ambiguous_unresolved": 1.0,
    "exhaustive_scope": 1.0,
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_REPOSITORY, text=True, capture_output=True, check=True
    ).stdout.strip()


def _matches(expected: list, claim) -> bool:
    subject, predicate, object_value, _ = expected
    if claim.predicate != predicate:
        return False
    if predicate == "alias":
        return {claim.normalized_subject, claim.normalized_object} == {subject, object_value}
    return claim.normalized_subject == subject and claim.normalized_object == object_value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--case", action="append", dest="case_ids")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == _REPOSITORY or _REPOSITORY in output.parents:
        parser.error("Acceptance output must be outside the source checkout")
    if _git("status", "--porcelain"):
        parser.error("Acceptance requires a clean immutable source checkout")
    revision = _git("rev-parse", "HEAD")
    provider_version = subprocess.run(
        ["codex", "--version"], text=True, capture_output=True, check=True
    ).stdout.strip()
    corpus_bytes = _CORPUS.read_bytes()
    corpus = json.loads(corpus_bytes)
    requested = set(args.case_ids or [])
    cases = [case for case in corpus["cases"] if not requested or case["id"] in requested]
    complete = len(cases) == len(corpus["cases"])
    sys.path.insert(0, str(_BUILDERS))
    from claim_fixture_builders import build_claim_case

    settings = Settings(provider="codex", codex_model=args.model, timeout_seconds=args.timeout)

    def build(stage: Path) -> dict[str, object]:
        records = []
        expected_total = matched_total = modality_total = modality_matched = 0
        alias_total = alias_matched = unresolved_total = unresolved_matched = 0
        exhaustive_total = exhaustive_matched = 0
        failures = []
        for case in cases:
            selection, diagram = build_claim_case(case)
            caller = CodexStructuredCaller(settings, DocumentClaimBatch)
            try:
                result = StructuredClaimExtractionWorkflow(caller).extract(selection)
                alignments = align_claim_entities(result.claims, diagram)
                matched_claim_ids = set()
                case_expected = len(case["expected"])
                case_matched = case_modality = 0
                for expected in case["expected"]:
                    expected_total += 1
                    modality_total += 1
                    match = next(
                        (claim for claim in result.claims.claims if _matches(expected, claim)),
                        None,
                    )
                    if match is not None:
                        matched_total += 1
                        case_matched += 1
                        matched_claim_ids.add(match.id)
                        if match.modality == expected[3]:
                            modality_matched += 1
                            case_modality += 1
                alias_entity = case.get("alias_entity")
                if alias_entity:
                    alias_total += 1
                    if any(
                        item.normalized_entity == alias_entity
                        and item.method == "explicit_alias"
                        for item in alignments.alignments
                    ):
                        alias_matched += 1
                unresolved = case.get("unresolved_entity")
                if unresolved:
                    unresolved_total += 1
                    if any(
                        item.normalized_entity == unresolved and item.method == "unresolved"
                        for item in alignments.alignments
                    ):
                        unresolved_matched += 1
                if case.get("require_exhaustive"):
                    exhaustive_total += 1
                    if any(
                        claim.exhaustive and claim.scope == "current_figure"
                        for claim in result.claims.claims
                    ):
                        exhaustive_matched += 1
                record = {
                    "id": case["id"],
                    "status": "completed",
                    "expected": case_expected,
                    "matched": case_matched,
                    "modality_matched": case_modality,
                    "result": result.model_dump(mode="json"),
                    "alignments": alignments.model_dump(mode="json"),
                }
            except Exception as error:
                failure = {"id": case["id"], "error": f"{type(error).__name__}: {error}"}
                failures.append(failure)
                record = {"id": case["id"], "status": "failed", "failure": failure}
            records.append(record)
        metrics = {
            "claim_recall": matched_total / expected_total if expected_total else 1.0,
            "modality_accuracy": modality_matched / modality_total if modality_total else 1.0,
            "exact_span_validity": 1.0 if not failures else 0.0,
            "alias_alignment": alias_matched / alias_total if alias_total else 1.0,
            "ambiguous_unresolved": (
                unresolved_matched / unresolved_total if unresolved_total else 1.0
            ),
            "exhaustive_scope": (
                exhaustive_matched / exhaustive_total if exhaustive_total else 1.0
            ),
        }
        passed = complete and not failures and all(
            metrics[name] >= threshold for name, threshold in _THRESHOLDS.items()
        )
        report = {
            "status": "passed" if passed else ("exploratory" if not complete else "failed"),
            "source_revision": revision,
            "source_clean": True,
            "provider": "codex-cli",
            "provider_version": provider_version,
            "model": args.model,
            "corpus_version": corpus["version"],
            "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
            "complete_corpus": complete,
            "thresholds": _THRESHOLDS,
            "metrics": metrics,
            "failures": failures,
            "cases": records,
        }
        (stage / "acceptance-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        return report

    report = publish_artifact_directory(output, build)
    print(f"A5 claim acceptance: {report['status']}")
    print(f"Evidence: {output}")
    return 0 if report["status"] in {"passed", "exploratory"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
