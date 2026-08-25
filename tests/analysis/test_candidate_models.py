"""Validation tests for strict A2 candidate contracts."""

import pytest
from pydantic import ValidationError

from visiogen.analysis.models import (
    CandidateCoverage,
    CandidateDecision,
    DiagramCandidate,
)


def test_unknown_decision_requires_unknown_confidence() -> None:
    with pytest.raises(ValidationError, match="unknown confidence"):
        CandidateDecision(
            candidate_id="candidate-0001",
            label="unknown",
            confidence="low",
            reason="Unclear pixels",
            classifier="test",
        )


def test_candidate_references_and_disposition_are_validated() -> None:
    decision = CandidateDecision(
        candidate_id="candidate-0001",
        label="non_diagram",
        confidence="high",
        reason="Decorative rule",
        classifier="test",
    )
    with pytest.raises(ValidationError, match="cannot be selected"):
        DiagramCandidate(
            id="candidate-0001",
            primary_asset_id="asset-1",
            source_asset_ids=["asset-1"],
            width_px=100,
            height_px=100,
            decision=decision,
            disposition="selected",
            disposition_reason="Selected",
        )


def test_candidate_coverage_must_account_for_every_asset() -> None:
    with pytest.raises(ValidationError, match="cover every candidate"):
        CandidateCoverage(
            source_assets=2,
            unique_candidates=2,
            duplicate_assets_grouped=0,
            selected=1,
            ignored_non_diagram=0,
            awaiting_classification=0,
            filtered_out=0,
            skipped_limit=0,
        )
