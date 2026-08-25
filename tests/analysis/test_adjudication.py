"""Bounded A6 semantic-adjudication contract and workflow tests."""

import json

import pytest

from visiogen.analysis.adjudication import (
    AdjudicationDecision,
    AdjudicationWorkflowError,
    StructuredAdjudicationWorkflow,
    apply_adjudication_decision,
    build_adjudication_request,
)
from visiogen.analysis.claims import DocumentClaimBatch
from visiogen.analysis.comparison import ConsistencyFinding
from visiogen.analysis.semantics import AnalyzedDiagram
from visiogen.providers.base import ProviderResponse


class FakeCall:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return ProviderResponse(content=next(self.responses), elapsed_ms=4)


def _sources() -> tuple[ConsistencyFinding, AnalyzedDiagram, DocumentClaimBatch]:
    diagram = AnalyzedDiagram.model_validate(
        {
            "candidate_id": "candidate-0001",
            "family": "system_block",
            "orientation": "left_to_right",
            "objects": [
                {
                    "id": "object-0001",
                    "visible_label": "DB",
                    "normalized_label": "db",
                    "semantic_type": "store",
                    "visual_shape": "cylinder",
                    "bbox": {"left": 0.1, "top": 0.1, "right": 0.3, "bottom": 0.3},
                    "evidence_ids": ["evidence-0001"],
                    "confidence": "high",
                }
            ],
            "relationships": [],
            "confidence": "high",
        }
    )
    batch = DocumentClaimBatch.model_validate(
        {
            "candidate_id": "candidate-0001",
            "evidence": [
                {
                    "id": "text-evidence-0001",
                    "block_id": "text-0001",
                    "exact_text": "The database stores records.",
                    "start": 0,
                    "end": 28,
                }
            ],
            "claims": [
                {
                    "id": "claim-0001",
                    "subject_text": "database",
                    "normalized_subject": "database",
                    "predicate": "attribute_or_state",
                    "object_text": "stores records",
                    "normalized_object": "stores records",
                    "modality": "asserted",
                    "scope": "current_figure",
                    "refers_to_candidate": "yes",
                    "evidence_ids": ["text-evidence-0001"],
                    "confidence": "high",
                }
            ],
        }
    )
    finding = ConsistencyFinding(
        id="finding-0001",
        category="unsupported_claim",
        status="needs_human_review",
        severity="warning",
        diagram_fact={"subject": "db", "predicate": "type_or_role", "object_or_value": "store"},
        text_claim={"subject": "database", "predicate": "attribute_or_state", "object_or_value": "stores records"},
        claim_id="claim-0001",
        diagram_evidence_ids=["evidence-0001"],
        text_evidence_ids=["text-evidence-0001"],
        explanation="Exact rules cannot establish semantic equivalence.",
        confidence="unknown",
        uncertainty="DB may or may not mean database in this domain.",
        review_action="Confirm the abbreviation.",
    )
    return finding, diagram, batch


def _decision(*, finding_id: str = "finding-0001") -> str:
    return AdjudicationDecision(
        finding_id=finding_id,
        status="terminology_difference",
        explanation="DB and database are likely equivalent labels.",
        confidence="medium",
        review_action="Confirm the domain abbreviation.",
    ).model_dump_json()


def test_request_contains_only_the_single_finding_and_its_cited_evidence() -> None:
    finding, diagram, batch = _sources()

    request = build_adjudication_request(finding, diagram, batch)

    assert request.finding_id == finding.id
    assert {item.evidence_id for item in request.evidence} == {
        "evidence-0001",
        "text-evidence-0001",
    }
    assert "The database stores records." in request.model_dump_json()


def test_workflow_rejects_wrong_finding_id_then_repairs_once() -> None:
    finding, diagram, batch = _sources()
    request = build_adjudication_request(finding, diagram, batch)
    caller = FakeCall([_decision(finding_id="finding-9999"), _decision()])

    result = StructuredAdjudicationWorkflow(caller).adjudicate(request)

    assert result.attempts == 2
    assert result.decision.status == "terminology_difference"
    assert "Do not add evidence or strengthen the outcome" in caller.calls[1][1]


def test_workflow_never_permits_model_confirmed_contradiction() -> None:
    finding, diagram, batch = _sources()
    request = build_adjudication_request(finding, diagram, batch)
    invalid = json.dumps(
        {
            "finding_id": "finding-0001",
            "status": "confirmed_contradiction",
            "explanation": "No.",
            "confidence": "high",
            "review_action": "Review.",
        }
    )

    with pytest.raises(AdjudicationWorkflowError) as captured:
        StructuredAdjudicationWorkflow(FakeCall([invalid, invalid])).adjudicate(request)

    assert len(captured.value.traces) == 2
    assert captured.value.validation_error


def test_decision_updates_only_review_fields_and_preserves_evidence() -> None:
    finding, _, _ = _sources()
    decision = AdjudicationDecision.model_validate_json(_decision())

    updated = apply_adjudication_decision(finding, decision)

    assert updated.status == "terminology_difference"
    assert updated.diagram_fact == finding.diagram_fact
    assert updated.text_claim == finding.text_claim
    assert updated.diagram_evidence_ids == finding.diagram_evidence_ids
    assert updated.text_evidence_ids == finding.text_evidence_ids


def test_request_rejects_missing_or_cross_candidate_evidence() -> None:
    finding, diagram, batch = _sources()
    finding.diagram_evidence_ids = ["evidence-9999"]

    with pytest.raises(ValueError, match="unavailable evidence"):
        build_adjudication_request(finding, diagram, batch)

    finding.diagram_evidence_ids = ["evidence-0001"]
    batch.candidate_id = "candidate-0002"
    with pytest.raises(ValueError, match="different candidate IDs"):
        build_adjudication_request(finding, diagram, batch)


def test_annotation_evidence_is_available_to_bounded_adjudication() -> None:
    finding, diagram, batch = _sources()
    payload = diagram.model_dump(mode="json")
    payload["annotations"] = [
        {
            "id": "annotation-0001",
            "kind": "callout",
            "visible_text": "DB stores records",
            "attached_object_ids": ["object-0001"],
            "bbox": {"left": 0.3, "top": 0.1, "right": 0.6, "bottom": 0.2},
            "evidence_ids": ["evidence-0002"],
            "confidence": "high",
        }
    ]
    diagram = AnalyzedDiagram.model_validate(payload)
    finding.diagram_evidence_ids = ["evidence-0002"]

    request = build_adjudication_request(finding, diagram, batch)

    assert "DB stores records" in request.model_dump_json()
