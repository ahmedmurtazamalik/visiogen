"""Generate A8 blinded-review packets from checksum-bound execution evidence."""

from __future__ import annotations

from typing import Any

from visiogen.analysis.release_evaluation import ReleaseCase


def build_review_packet(
    cases: list[ReleaseCase], execution: dict[str, Any]
) -> dict[str, Any]:
    """Create held-out review forms bound to exact completed analysis bundles."""

    if execution.get("status") != "passed" or execution.get("complete_corpus") is not True:
        raise ValueError("Review packets require a passing complete-corpus execution")
    executed = execution.get("cases")
    if not isinstance(executed, list):
        raise ValueError("Execution case records are missing")
    executed_by_id: dict[str, dict[str, Any]] = {}
    for item in executed:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            raise ValueError("Execution contains an invalid case record")
        if item["case_id"] in executed_by_id:
            raise ValueError(f"Duplicate execution case: {item['case_id']}")
        executed_by_id[item["case_id"]] = item
    if set(executed_by_id) != {case.id for case in cases}:
        raise ValueError("Execution cases do not exactly match the corpus")
    reviews: list[dict[str, Any]] = []
    for case in cases:
        if case.subset != "held_out":
            continue
        outcome = executed_by_id[case.id]
        bundle_sha = outcome.get("bundle_sha256")
        if outcome.get("status") != "complete" or not isinstance(bundle_sha, str):
            raise ValueError(f"Held-out execution is not complete and hash-bound: {case.id}")
        reviews.append(
            {
                "case_id": case.id,
                "analysis_bundle_sha256": bundle_sha,
                "diagram": {
                    "reviewer_id": None,
                    "prose_was_hidden": None,
                    "schema_reference_valid": None,
                    "expected_visible_labels": None,
                    "correct_visible_labels": None,
                    "invented_visible_labels_or_references": None,
                    "object_relationship_true_positive": None,
                    "object_relationship_false_positive": None,
                    "object_relationship_false_negative": None,
                    "forced_unclear_directions": None,
                    "unsupported_inferences": None,
                },
                "consistency": {
                    "reviewer_id": None,
                    "confirmed_contradiction_true_positive": None,
                    "confirmed_contradiction_false_positive": None,
                    "confirmed_contradiction_false_negative": None,
                    "reported_contradictions": None,
                    "contradictions_with_valid_dual_evidence": None,
                    "non_exhaustive_omission_false_positives": None,
                },
                "degraded_modalities_reported": None,
                "provenance_suppressed": None,
                "reviewer_notes": [],
            }
        )
    return {
        "instructions": {
            "diagram_pass": (
                "Hide all document prose. Review only source diagram pixels, analyzed-diagram "
                "JSON, and the generated diagram description."
            ),
            "consistency_pass": (
                "Use both diagram pixels and cited document passages. A reviewer different "
                "from the diagram-pass reviewer must complete this section."
            ),
            "completion": (
                "Replace every null with a reviewed value. Do not change case IDs or bundle "
                "hashes. The release scorer rejects incomplete records."
            ),
        },
        "source_revision": execution.get("source_revision"),
        "provider": execution.get("provider"),
        "model": execution.get("model"),
        "reviews": reviews,
    }
