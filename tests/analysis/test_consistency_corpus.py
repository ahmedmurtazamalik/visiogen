"""Execute every reviewed A6 positive, negative, and ambiguous control."""

import json
from pathlib import Path

import pytest

from consistency_fixture_builders import build_consistency_case
from visiogen.analysis.comparison import compare_diagram_and_claims
from visiogen.analysis.comparison_evaluation import (
    aggregate_consistency_scores,
    score_consistency_case,
)

_CORPUS = Path(__file__).parents[1] / "fixtures/analysis/consistency_corpus.json"
_CASES = json.loads(_CORPUS.read_text())["cases"]


def test_consistency_corpus_is_the_complete_three_variant_matrix() -> None:
    categories = {case["category"] for case in _CASES}
    assert len(categories) == 13
    assert len(_CASES) == 39
    for category in categories:
        assert {case["variant"] for case in _CASES if case["category"] == category} == {
            "contradiction",
            "consistent",
            "ambiguous",
        }


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_controlled_consistency_case_matches_reviewed_outcome(case: dict) -> None:
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

    assert score.matched, analysis.model_dump(mode="json")
    assert score.evidence_complete
    assert not score.non_exhaustive_omission_false_positive


def test_controlled_corpus_meets_all_a6_release_gates() -> None:
    scores = []
    for case in _CASES:
        diagram, batch, alignments = build_consistency_case(case)
        analysis = compare_diagram_and_claims(
            diagram,
            batch,
            alignments,
            strict_coverage=case["exhaustive_scope"],
        )
        scores.append(
            score_consistency_case(
                case["id"],
                case["expected_category"],
                case["expected_status"],
                analysis,
                exhaustive_scope=case["exhaustive_scope"],
            )
        )

    aggregate = aggregate_consistency_scores(scores)

    assert aggregate.case_accuracy == 1
    assert aggregate.confirmed_contradiction_precision >= 0.90
    assert aggregate.evidence_validity == 1
    assert aggregate.non_exhaustive_omission_false_positives == 0
