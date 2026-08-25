"""Deterministic scoring for the controlled A6 consistency matrix."""

from __future__ import annotations

from pydantic import Field

from visiogen.analysis.comparison import ConsistencyAnalysis
from visiogen.analysis.models import AnalysisModel


class ConsistencyCaseScore(AnalysisModel):
    case_id: str = Field(min_length=1)
    expected_category: str = Field(min_length=1)
    expected_status: str = Field(min_length=1)
    matched: bool
    confirmed_contradictions: int = Field(ge=0)
    correct_confirmed_contradictions: int = Field(ge=0)
    evidence_complete: bool
    non_exhaustive_omission_false_positive: bool


class ConsistencyCorpusScore(AnalysisModel):
    case_accuracy: float = Field(ge=0, le=1)
    confirmed_contradiction_precision: float = Field(ge=0, le=1)
    evidence_validity: float = Field(ge=0, le=1)
    non_exhaustive_omission_false_positives: int = Field(ge=0)
    cases: list[ConsistencyCaseScore]


def score_consistency_case(
    case_id: str,
    expected_category: str,
    expected_status: str,
    analysis: ConsistencyAnalysis,
    *,
    exhaustive_scope: bool,
) -> ConsistencyCaseScore:
    """Score one expected category/status while tolerating unrelated internal warnings."""

    relevant = [item for item in analysis.findings if item.category == expected_category]
    matched = (
        not relevant
        if expected_status == "no_finding"
        else any(item.status == expected_status for item in relevant)
    )
    confirmed = [
        item for item in analysis.findings if item.status == "confirmed_contradiction"
    ]
    correct_confirmed = sum(
        item.category == expected_category and expected_status == "confirmed_contradiction"
        for item in confirmed
    )
    evidence_complete = all(
        bool(item.diagram_evidence_ids)
        and (
            item.status == "diagram_internal_warning"
            or (bool(item.text_evidence_ids) and item.claim_id is not None)
        )
        for item in analysis.findings
        if item.status != "unverifiable"
    )
    false_omission = not exhaustive_scope and any(
        item.status == "possible_omission" for item in analysis.findings
    )
    return ConsistencyCaseScore(
        case_id=case_id,
        expected_category=expected_category,
        expected_status=expected_status,
        matched=matched,
        confirmed_contradictions=len(confirmed),
        correct_confirmed_contradictions=correct_confirmed,
        evidence_complete=evidence_complete,
        non_exhaustive_omission_false_positive=false_omission,
    )


def aggregate_consistency_scores(
    scores: list[ConsistencyCaseScore],
) -> ConsistencyCorpusScore:
    """Aggregate the A6 precision and evidence gates without macro-averaging."""

    total_confirmed = sum(item.confirmed_contradictions for item in scores)
    correct_confirmed = sum(item.correct_confirmed_contradictions for item in scores)
    count = len(scores)
    return ConsistencyCorpusScore(
        case_accuracy=sum(item.matched for item in scores) / count if count else 1,
        confirmed_contradiction_precision=(
            correct_confirmed / total_confirmed if total_confirmed else 1
        ),
        evidence_validity=(
            sum(item.evidence_complete for item in scores) / count if count else 1
        ),
        non_exhaustive_omission_false_positives=sum(
            item.non_exhaustive_omission_false_positive for item in scores
        ),
        cases=scores,
    )
