"""Build evidence-complete production inputs for the controlled A6 matrix."""

from __future__ import annotations

from visiogen.analysis.claims import (
    DocumentClaim,
    DocumentClaimBatch,
    EntityAlignment,
    EntityAlignmentSet,
    TextClaimEvidence,
)
from visiogen.analysis.semantics import AnalyzedDiagram


def _object(
    index: int,
    label: str | None,
    reference: str,
    left: float,
    *,
    parent_id: str | None = None,
    confidence: str = "high",
) -> dict:
    return {
        "id": f"object-{index:04d}",
        "visible_label": label,
        "normalized_label": label.casefold() if label is not None else None,
        "semantic_type": "container" if index == 3 else "component",
        "visual_shape": "rectangle",
        "reference_numbers": [reference],
        "parent_id": parent_id,
        "bbox": (
            {"left": 0.02, "top": 0.05, "right": 0.98, "bottom": 0.9}
            if index == 3
            else {"left": left, "top": 0.2, "right": left + 0.2, "bottom": 0.4}
        ),
        "evidence_ids": [f"evidence-{index:04d}"],
        "confidence": confidence,
    }


def _relationship(
    index: int,
    source: int,
    target: int,
    *,
    direction: str = "forward",
    relation: str = "data",
) -> dict:
    return {
        "id": f"relationship-{index:04d}",
        "source_id": f"object-{source:04d}",
        "target_id": f"object-{target:04d}",
        "source_certainty": "known",
        "target_certainty": "known",
        "direction": direction,
        "relation": relation,
        "path": [{"x": 0.25, "y": 0.3}, {"x": 0.45, "y": 0.3}],
        "line_style": "solid",
        "evidence_ids": [f"evidence-{index + 3:04d}"],
        "confidence": "medium" if direction == "unclear" else "high",
    }


def build_consistency_case(
    case: dict,
) -> tuple[AnalyzedDiagram, DocumentClaimBatch, EntityAlignmentSet]:
    """Translate one reviewed compact case into strict A3/A5 contracts."""

    category = case["category"]
    variant = case["variant"]
    object_label: str | None = "Sensor 10"
    object_confidence = "high"
    if category == "unreadable_evidence" and variant == "ambiguous":
        object_label = None
        object_confidence = "low"
    elif category == "unreadable_evidence" and variant == "contradiction":
        object_confidence = "low"

    parent = "object-0003" if category == "containment" and variant == "consistent" else None
    objects = [
        _object(1, object_label, "10", 0.1, parent_id=parent, confidence=object_confidence),
        _object(2, "Processor 20", "20", 0.5),
        _object(3, "Platform 30", "30", 0.0),
    ]
    relationship_present = not (
        (category == "relationship" and variant == "contradiction")
        or (category == "modality" and variant in {"contradiction", "consistent"})
        or (category == "negation" and variant == "consistent")
    )
    direction = "forward"
    if category == "sequence" and variant == "contradiction":
        direction = "reverse"
    elif category in {"sequence", "direction"} and variant == "ambiguous":
        direction = "unclear"
    relation = (
        "control"
        if category == "relationship_type" and variant == "contradiction"
        else "data"
    )
    relationships = (
        [_relationship(1, 1, 2, direction=direction, relation=relation)]
        if relationship_present
        else []
    )
    if category == "relationship_type" and variant == "ambiguous":
        relationships.append(_relationship(2, 1, 3, relation="control"))

    diagram = AnalyzedDiagram.model_validate(
        {
            "candidate_id": "candidate-0001",
            "family": "system_block",
            "orientation": "left_to_right",
            "objects": objects,
            "relationships": relationships,
            "limitations": (
                ["The Sensor 10 label is unreadable at the available resolution."]
                if category == "unreadable_evidence" and variant == "ambiguous"
                else []
            ),
            "confidence": "low"
            if category == "unreadable_evidence" and variant == "ambiguous"
            else "high",
        }
    )

    claims: list[DocumentClaim] = []
    evidence: list[TextClaimEvidence] = []
    alignments: list[EntityAlignment] = []

    def add_claim(
        subject: str,
        predicate: str,
        object_value: str | None,
        *,
        modality: str = "asserted",
        exhaustive: bool = False,
        subject_object_id: str | None = "object-0001",
        object_object_id: str | None = None,
    ) -> None:
        number = len(claims) + 1
        claim_id = f"claim-{number:04d}"
        evidence_id = f"text-evidence-{number:04d}"
        exact_text = f"{subject} {predicate} {object_value or ''}".strip()
        evidence.append(
            TextClaimEvidence(
                id=evidence_id,
                block_id=f"text-{number:04d}",
                exact_text=exact_text,
                start=0,
                end=len(exact_text),
            )
        )
        claims.append(
            DocumentClaim(
                id=claim_id,
                subject_text=subject,
                normalized_subject=subject.casefold(),
                predicate=predicate,
                object_text=object_value,
                normalized_object=object_value.casefold() if object_value is not None else None,
                modality=modality,
                scope="current_figure",
                exhaustive=exhaustive,
                refers_to_candidate="yes",
                evidence_ids=[evidence_id],
                confidence="high",
            )
        )
        alignments.append(
            EntityAlignment(
                claim_id=claim_id,
                entity_role="subject",
                entity_text=subject,
                normalized_entity=subject.casefold(),
                object_id=subject_object_id,
                method=(
                    "exact_reference"
                    if subject_object_id is not None and subject != (object_label or "")
                    else "exact_label"
                    if subject_object_id is not None
                    else "unresolved"
                ),
                score=1 if subject_object_id is not None else 0,
                evidence_ids=[evidence_id],
            )
        )
        if predicate in {"alias", "contains", "connects_to", "sequence"}:
            alignments.append(
                EntityAlignment(
                    claim_id=claim_id,
                    entity_role="object",
                    entity_text=object_value or "unknown",
                    normalized_entity=(object_value or "unknown").casefold(),
                    object_id=object_object_id,
                    method="exact_label" if object_object_id is not None else "unresolved",
                    score=1 if object_object_id is not None else 0,
                    evidence_ids=[evidence_id],
                )
            )

    if category == "label":
        add_claim(
            "Motor 10" if variant == "contradiction" else "Sensor 10" if variant == "consistent" else "Device",
            "exists",
            None,
            subject_object_id="object-0001" if variant != "ambiguous" else None,
        )
    elif category == "reference_number":
        add_claim(
            "Sensor 10" if variant != "ambiguous" else "Device",
            "reference_mapping",
            "11" if variant == "contradiction" else "10",
            subject_object_id="object-0001" if variant != "ambiguous" else None,
        )
    elif category == "object_existence":
        add_claim(
            "Sensor 10" if variant != "ambiguous" else "Device",
            "not_exists" if variant == "contradiction" else "exists",
            None,
            modality="negated" if variant == "contradiction" else "asserted",
            subject_object_id="object-0001" if variant != "ambiguous" else None,
        )
    elif category in {"relationship", "modality", "negation"}:
        modality = (
            "possible"
            if category == "modality" and variant == "consistent"
            else "unknown"
            if category == "modality" and variant == "ambiguous"
            else "negated"
            if category == "negation"
            else "required"
        )
        unresolved = variant == "ambiguous" and category in {"relationship", "negation"}
        add_claim(
            "Sensor 10",
            "connects_to",
            "Processor 20",
            modality=modality,
            object_object_id=None if unresolved else "object-0002",
        )
    elif category in {"direction", "relationship_type"}:
        value = (
            "reverse"
            if category == "direction" and variant == "contradiction"
            else "forward"
            if category == "direction"
            else "power"
            if variant == "contradiction"
            else "data"
        )
        add_claim("Sensor 10", category, value)
    elif category == "containment":
        add_claim(
            "Platform 30",
            "contains",
            "Sensor 10" if variant != "ambiguous" else "Device",
            subject_object_id="object-0003",
            object_object_id="object-0001" if variant != "ambiguous" else None,
        )
    elif category == "sequence":
        add_claim(
            "Sensor 10",
            "sequence",
            "Processor 20",
            object_object_id="object-0002",
        )
    elif category == "alias":
        add_claim(
            "Sensor 10",
            "alias",
            "Probe" if variant != "contradiction" else "Processor 20",
            object_object_id=(
                "object-0001"
                if variant == "consistent"
                else "object-0002"
                if variant == "contradiction"
                else None
            ),
        )
    elif category == "exhaustive_scope":
        if variant == "consistent":
            for index, label in enumerate(("Sensor 10", "Processor 20", "Platform 30"), start=1):
                add_claim(
                    label,
                    "exists",
                    None,
                    exhaustive=True,
                    subject_object_id=f"object-{index:04d}",
                )
        else:
            add_claim(
                "Sensor 10",
                "exists",
                None,
                exhaustive=variant == "contradiction",
            )
    elif category == "unreadable_evidence":
        add_claim(
            "Motor 10" if variant == "contradiction" else "Sensor 10",
            "exists",
            None,
            subject_object_id=None if variant == "ambiguous" else "object-0001",
        )
    else:
        raise ValueError(f"Unknown consistency category: {category}")

    batch = DocumentClaimBatch(
        candidate_id="candidate-0001",
        evidence=evidence,
        claims=claims,
    )
    alignment_set = EntityAlignmentSet(
        candidate_id="candidate-0001",
        alignments=alignments,
    )
    return diagram, batch, alignment_set
