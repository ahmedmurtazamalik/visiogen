"""A6 deterministic comparison and evidence-policy tests."""

import pytest
from pydantic import ValidationError

from visiogen.analysis.claims import (
    DocumentClaim,
    DocumentClaimBatch,
    EntityAlignment,
    EntityAlignmentSet,
    TextClaimEvidence,
)
from visiogen.analysis.comparison import (
    ConsistencyFinding,
    compare_diagram_and_claims,
    render_findings_markdown,
)
from visiogen.analysis.semantics import AnalyzedDiagram


def _diagram(
    *,
    relationship: bool = True,
    extra: bool = False,
    direction: str = "forward",
    relation: str = "data",
) -> AnalyzedDiagram:
    objects = [
        {
            "id": "object-0001",
            "visible_label": "Sensor 10",
            "normalized_label": "sensor 10",
            "semantic_type": "sensor",
            "visual_shape": "rectangle",
            "reference_numbers": ["10"],
            "bbox": {"left": 0.05, "top": 0.2, "right": 0.25, "bottom": 0.4},
            "evidence_ids": ["evidence-0001"],
            "confidence": "high",
        },
        {
            "id": "object-0002",
            "visible_label": "Processor 20",
            "normalized_label": "processor 20",
            "semantic_type": "processor",
            "visual_shape": "rectangle",
            "reference_numbers": ["20"],
            "bbox": {"left": 0.4, "top": 0.2, "right": 0.6, "bottom": 0.4},
            "evidence_ids": ["evidence-0002"],
            "confidence": "high",
        },
    ]
    if extra:
        objects.append(
            {
                "id": "object-0003",
                "visible_label": "Archive 30",
                "normalized_label": "archive 30",
                "semantic_type": "store",
                "visual_shape": "rectangle",
                "reference_numbers": ["30"],
                "bbox": {"left": 0.7, "top": 0.2, "right": 0.9, "bottom": 0.4},
                "evidence_ids": ["evidence-0003"],
                "confidence": "high",
            }
        )
    relationships = []
    if relationship:
        relationships.append(
            {
                "id": "relationship-0001",
                "source_id": "object-0001",
                "target_id": "object-0002",
                "source_certainty": "known",
                "target_certainty": "known",
                "direction": direction,
                "relation": relation,
                "path": [{"x": 0.25, "y": 0.3}, {"x": 0.4, "y": 0.3}],
                "line_style": "solid",
                "evidence_ids": ["evidence-0004"],
                "confidence": "medium" if direction == "unclear" else "high",
            }
        )
    return AnalyzedDiagram.model_validate(
        {
            "candidate_id": "candidate-0001",
            "family": "system_block",
            "orientation": "left_to_right",
            "objects": objects,
            "relationships": relationships,
            "confidence": "high",
        }
    )


def _claim(
    *,
    predicate: str = "connects_to",
    modality: str = "asserted",
    exhaustive: bool = False,
    subject: str = "Sensor 10",
    object_value: str | None = None,
) -> DocumentClaim:
    default_object = "Processor 20" if predicate in {"connects_to", "sequence"} else None
    object_text = object_value if object_value is not None else default_object
    return DocumentClaim.model_validate(
        {
            "id": "claim-0001",
            "subject_text": subject,
            "normalized_subject": subject.casefold(),
            "predicate": predicate,
            "object_text": object_text,
            "normalized_object": object_text.casefold() if object_text is not None else None,
            "modality": modality,
            "scope": "current_figure",
            "exhaustive": exhaustive,
            "refers_to_candidate": "yes",
            "evidence_ids": ["text-evidence-0001"],
            "confidence": "high",
        }
    )


def _inputs(
    diagram: AnalyzedDiagram,
    claim: DocumentClaim,
    *,
    resolve_object: bool = True,
) -> tuple[DocumentClaimBatch, EntityAlignmentSet]:
    batch = DocumentClaimBatch(
        candidate_id="candidate-0001",
        evidence=[
            TextClaimEvidence(
                id="text-evidence-0001",
                block_id="text-0001",
                exact_text="Sensor 10 connects to Processor 20.",
                start=0,
                end=35,
            )
        ],
        claims=[claim],
    )
    alignments = [
        EntityAlignment(
            claim_id=claim.id,
            entity_role="subject",
            entity_text=claim.subject_text,
            normalized_entity=claim.normalized_subject,
            object_id="object-0001",
            method="exact_reference",
            score=1,
            evidence_ids=claim.evidence_ids,
        )
    ]
    if claim.predicate in {"alias", "contains", "connects_to", "sequence"}:
        alignments.append(
            EntityAlignment(
                claim_id=claim.id,
                entity_role="object",
                entity_text=claim.object_text,
                normalized_entity=claim.normalized_object or "",
                object_id="object-0002" if resolve_object else None,
                method="exact_reference" if resolve_object else "unresolved",
                score=1 if resolve_object else 0,
                evidence_ids=claim.evidence_ids,
            )
        )
    return batch, EntityAlignmentSet(candidate_id=diagram.candidate_id, alignments=alignments)


def test_visible_relationship_is_confirmed_consistent_with_both_evidence_sides() -> None:
    diagram = _diagram()
    claim = _claim()
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    finding = next(item for item in result.findings if item.category == "relationship")
    assert finding.status == "confirmed_consistent"
    assert finding.diagram_evidence_ids == ["evidence-0004"]
    assert finding.text_evidence_ids == ["text-evidence-0001"]


def test_missing_required_relationship_is_probable_not_forced_confirmed() -> None:
    diagram = _diagram(relationship=False)
    claim = _claim(modality="required")
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    finding = result.findings[0]
    assert finding.status == "probable_contradiction"
    assert finding.uncertainty == "A faint, occluded, or unrecognized connector could account for the absence."


def test_possible_relationship_is_not_a_contradiction_when_connector_is_absent() -> None:
    diagram = _diagram(relationship=False)
    claim = _claim(modality="possible")
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    assert result.findings[0].status == "confirmed_consistent"


def test_unresolved_entity_is_unverifiable() -> None:
    diagram = _diagram()
    claim = _claim()
    batch, alignments = _inputs(diagram, claim, resolve_object=False)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    finding = next(item for item in result.findings if item.category == "relationship")
    assert finding.status == "unverifiable"
    assert finding.confidence == "unknown"


def test_non_exhaustive_prose_never_flags_unmentioned_diagram_object() -> None:
    diagram = _diagram(extra=True)
    claim = _claim()
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    assert all(item.status != "possible_omission" for item in result.findings)


def test_exhaustive_claim_flags_only_unaligned_objects_as_possible_omissions() -> None:
    diagram = _diagram(extra=True)
    claim = _claim(predicate="exists", exhaustive=True)
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    omissions = [item for item in result.findings if item.status == "possible_omission"]
    assert {item.diagram_fact.subject for item in omissions} == {"processor 20", "archive 30"}


def test_confirmed_contradiction_cannot_drop_text_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence from both sources"):
        ConsistencyFinding(
            id="finding-0001",
            category="object_existence",
            status="confirmed_contradiction",
            severity="error",
            diagram_fact={"subject": "sensor 10", "predicate": "exists"},
            text_claim={"subject": "sensor 10", "predicate": "not_exists"},
            claim_id="claim-0001",
            diagram_evidence_ids=["evidence-0001"],
            explanation="Contradiction.",
            confidence="high",
            review_action="Verify both sources.",
        )


def test_report_exposes_status_evidence_and_review_action() -> None:
    diagram = _diagram()
    claim = _claim()
    batch, alignments = _inputs(diagram, claim)

    report = render_findings_markdown(compare_diagram_and_claims(diagram, batch, alignments))

    assert "`confirmed_consistent`" in report
    assert "Diagram evidence: evidence-0004" in report
    assert "Review action:" in report


def test_reversed_sequence_is_a_confirmed_contradiction() -> None:
    diagram = _diagram(direction="reverse")
    claim = _claim(predicate="sequence")
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    finding = next(item for item in result.findings if item.category == "sequence")
    assert finding.status == "confirmed_contradiction"
    assert finding.confidence == "high"


def test_unclear_sequence_direction_remains_unverifiable() -> None:
    diagram = _diagram(direction="unclear")
    claim = _claim(predicate="sequence")
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    assert any(item.category == "ambiguous_direction" for item in result.findings)
    finding = next(item for item in result.findings if item.category == "sequence")
    assert finding.status == "unverifiable"


def test_wrong_relationship_type_is_a_confirmed_contradiction() -> None:
    diagram = _diagram(relation="control")
    claim = _claim(predicate="relationship_type", object_value="data")
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    finding = next(item for item in result.findings if item.category == "relationship_type")
    assert finding.status == "confirmed_contradiction"


def test_reference_number_mismatch_is_a_confirmed_contradiction() -> None:
    diagram = _diagram()
    claim = _claim(predicate="reference_mapping", object_value="11")
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    finding = next(item for item in result.findings if item.category == "reference_number")
    assert finding.status == "confirmed_contradiction"
    assert finding.diagram_fact.object_or_value == "10"


def test_exact_reference_identity_exposes_label_mismatch() -> None:
    diagram = _diagram()
    claim = _claim(predicate="exists", subject="Motor 10")
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    assert [(item.category, item.status) for item in result.findings] == [
        ("label", "confirmed_contradiction")
    ]


@pytest.mark.parametrize(
    ("relationship", "expected"),
    [(True, "confirmed_contradiction"), (False, "confirmed_consistent")],
)
def test_negated_relationship_respects_visible_presence(
    relationship: bool,
    expected: str,
) -> None:
    diagram = _diagram(relationship=relationship)
    claim = _claim(modality="negated")
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    finding = next(item for item in result.findings if item.category == "negation")
    assert finding.status == expected


def test_cardinality_counts_only_visible_incident_relationships() -> None:
    diagram = _diagram()
    claim = _claim(predicate="cardinality", object_value="1")
    batch, alignments = _inputs(diagram, claim)

    result = compare_diagram_and_claims(diagram, batch, alignments)

    finding = next(item for item in result.findings if item.category == "cardinality")
    assert finding.status == "confirmed_consistent"
