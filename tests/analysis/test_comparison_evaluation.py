"""A6 controlled-matrix gate scoring tests."""

from visiogen.analysis.comparison import ConsistencyAnalysis, ConsistencyFinding
from visiogen.analysis.comparison_evaluation import (
    aggregate_consistency_scores,
    score_consistency_case,
)


def _analysis(status: str, category: str = "label") -> ConsistencyAnalysis:
    severity = {
        "confirmed_contradiction": "error",
        "confirmed_consistent": "info",
        "possible_omission": "warning",
    }[status]
    return ConsistencyAnalysis(
        candidate_id="candidate-0001",
        findings=[
            ConsistencyFinding(
                id="finding-0001",
                category=category,
                status=status,
                severity=severity,
                diagram_fact={"subject": "sensor", "predicate": "visible_label"},
                text_claim={"subject": "motor", "predicate": "exists"},
                claim_id="claim-0001",
                diagram_evidence_ids=["evidence-0001"],
                text_evidence_ids=["text-evidence-0001"],
                explanation="Controlled comparison.",
                confidence="high",
                review_action="Review both sources.",
            )
        ],
    )


def test_aggregate_scores_precision_evidence_and_omission_gate() -> None:
    contradiction = score_consistency_case(
        "label_contradiction",
        "label",
        "confirmed_contradiction",
        _analysis("confirmed_contradiction"),
        exhaustive_scope=False,
    )
    omission = score_consistency_case(
        "exhaustive_omission",
        "exhaustive_scope",
        "possible_omission",
        _analysis("possible_omission", "exhaustive_scope"),
        exhaustive_scope=True,
    )

    score = aggregate_consistency_scores([contradiction, omission])

    assert score.case_accuracy == 1
    assert score.confirmed_contradiction_precision == 1
    assert score.evidence_validity == 1
    assert score.non_exhaustive_omission_false_positives == 0


def test_non_exhaustive_omission_is_counted_as_a_gate_failure() -> None:
    score = score_consistency_case(
        "bad_omission",
        "exhaustive_scope",
        "no_finding",
        _analysis("possible_omission", "exhaustive_scope"),
        exhaustive_scope=False,
    )

    assert not score.matched
    assert score.non_exhaustive_omission_false_positive
