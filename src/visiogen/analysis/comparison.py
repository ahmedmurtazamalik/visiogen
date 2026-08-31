"""Evidence-first deterministic consistency analysis for A6."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import Field, model_validator

from visiogen.analysis.claim_validation import normalize_claim_text
from visiogen.analysis.claims import (
    DocumentClaim,
    DocumentClaimBatch,
    EntityAlignment,
    EntityAlignmentSet,
)
from visiogen.analysis.models import AnalysisModel, Confidence
from visiogen.analysis.semantics import (
    AnalyzedDiagram,
    AnalyzedObject,
    AnalyzedRelationship,
)

FindingCategory = Literal[
    "label",
    "reference_number",
    "object_existence",
    "relationship",
    "direction",
    "relationship_type",
    "containment",
    "sequence",
    "cardinality",
    "title",
    "terminology",
    "modality",
    "negation",
    "alias",
    "exhaustive_scope",
    "unreadable_evidence",
    "duplicate_reference",
    "dangling_connector",
    "ambiguous_direction",
    "container_geometry",
    "isolated_object",
    "unsupported_claim",
]
FindingStatus = Literal[
    "confirmed_consistent",
    "confirmed_contradiction",
    "probable_contradiction",
    "possible_omission",
    "terminology_difference",
    "diagram_internal_warning",
    "unverifiable",
    "needs_human_review",
]
FindingSeverity = Literal["info", "warning", "error"]


class ComparisonProposition(AnalysisModel):
    """One normalized proposition used in an auditable comparison."""

    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object_or_value: str | None = None
    qualifiers: list[str] = Field(default_factory=list)


class ConsistencyFinding(AnalysisModel):
    """One evidence-bound consistency result or diagram-internal warning."""

    id: str = Field(pattern=r"^finding-[0-9]{4}$")
    category: FindingCategory
    status: FindingStatus
    severity: FindingSeverity
    diagram_fact: ComparisonProposition
    text_claim: ComparisonProposition | None = None
    claim_id: str | None = None
    diagram_evidence_ids: list[str] = Field(default_factory=list)
    text_evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=1)
    confidence: Confidence
    uncertainty: str | None = None
    review_action: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence_policy(self) -> ConsistencyFinding:
        if len(self.diagram_evidence_ids) != len(set(self.diagram_evidence_ids)):
            raise ValueError("Finding diagram evidence IDs must be unique")
        if len(self.text_evidence_ids) != len(set(self.text_evidence_ids)):
            raise ValueError("Finding text evidence IDs must be unique")
        internal = self.status == "diagram_internal_warning"
        if internal and not self.diagram_evidence_ids:
            raise ValueError("Diagram-internal findings require diagram evidence")
        if internal and (self.text_claim is not None or self.claim_id is not None):
            raise ValueError("Diagram-internal findings cannot cite a text claim")
        if not internal and self.text_claim is None:
            raise ValueError("Cross-source findings require a normalized text proposition")
        if self.text_claim is not None and self.claim_id is None:
            raise ValueError("Text propositions require their source claim ID")
        if self.status in {
            "confirmed_consistent",
            "confirmed_contradiction",
            "probable_contradiction",
            "possible_omission",
            "terminology_difference",
        } and (not self.diagram_evidence_ids or not self.text_evidence_ids):
            raise ValueError("Decisive cross-source findings require evidence from both sources")
        if self.status == "confirmed_contradiction" and self.severity != "error":
            raise ValueError("Confirmed contradictions require error severity")
        if self.status == "confirmed_consistent" and self.severity != "info":
            raise ValueError("Confirmed consistency requires info severity")
        expected_severity = {
            "probable_contradiction": "warning",
            "possible_omission": "warning",
            "terminology_difference": "info",
            "diagram_internal_warning": "warning",
            "unverifiable": "warning",
            "needs_human_review": "warning",
        }.get(self.status)
        if expected_severity is not None and self.severity != expected_severity:
            raise ValueError(f"{self.status} requires {expected_severity} severity")
        if self.status in {
            "probable_contradiction",
            "unverifiable",
            "needs_human_review",
        } and not self.uncertainty:
            raise ValueError("Unresolved findings must explain their uncertainty")
        if self.status == "confirmed_contradiction" and self.confidence in {"low", "unknown"}:
            raise ValueError("Confirmed contradictions require medium or high confidence")
        return self


class ConsistencyAnalysis(AnalysisModel):
    """Validated A6 comparison result for one diagram candidate."""

    candidate_id: str = Field(min_length=1)
    strict_coverage: bool = False
    findings: list[ConsistencyFinding]

    @model_validator(mode="after")
    def validate_ids(self) -> ConsistencyAnalysis:
        ids = [finding.id for finding in self.findings]
        if len(ids) != len(set(ids)):
            raise ValueError("Consistency finding IDs must be unique")
        return self


def _claim_proposition(claim: DocumentClaim) -> ComparisonProposition:
    return ComparisonProposition(
        subject=claim.normalized_subject,
        predicate=claim.predicate,
        object_or_value=claim.normalized_object,
        qualifiers=[claim.modality, claim.scope, *claim.qualifiers],
    )


def _object_fact(item: AnalyzedObject, predicate: str = "exists") -> ComparisonProposition:
    return ComparisonProposition(
        subject=item.normalized_label or item.id,
        predicate=predicate,
        object_or_value=item.semantic_type if predicate == "type_or_role" else None,
    )


def _relationship_fact(
    relationship: AnalyzedRelationship,
    objects: dict[str, AnalyzedObject],
) -> ComparisonProposition:
    source = objects.get(relationship.source_id or "")
    target = objects.get(relationship.target_id or "")
    return ComparisonProposition(
        subject=(source.normalized_label if source else None) or relationship.source_id or "unknown",
        predicate="connects_to",
        object_or_value=(target.normalized_label if target else None)
        or relationship.target_id
        or "unknown",
        qualifiers=[relationship.direction, relationship.relation],
    )


def _contains(outer: AnalyzedObject, inner: AnalyzedObject) -> bool:
    return (
        inner.bbox.left >= outer.bbox.left
        and inner.bbox.top >= outer.bbox.top
        and inner.bbox.right <= outer.bbox.right
        and inner.bbox.bottom <= outer.bbox.bottom
    )


def _alignment_map(alignments: EntityAlignmentSet) -> dict[tuple[str, str], EntityAlignment]:
    return {(item.claim_id, item.entity_role): item for item in alignments.alignments}


def _validate_alignment_references(
    diagram: AnalyzedDiagram,
    batch: DocumentClaimBatch,
    alignments: EntityAlignmentSet,
) -> None:
    """Reject incomplete or cross-wired alignment inputs before comparison."""

    claims = {item.id: item for item in batch.claims}
    object_ids = {item.id for item in diagram.objects}
    expected: set[tuple[str, str]] = set()
    for claim in batch.claims:
        if claim.predicate not in {"figure_title", "figure_purpose"}:
            expected.add((claim.id, "subject"))
        if claim.predicate in {"alias", "contains", "connects_to", "sequence"}:
            expected.add((claim.id, "object"))
    actual = {(item.claim_id, item.entity_role) for item in alignments.alignments}
    errors = []
    if missing := expected - actual:
        errors.append(f"Missing entity alignments {sorted(missing)}")
    if extra := actual - expected:
        errors.append(f"Unexpected entity alignments {sorted(extra)}")
    for alignment in alignments.alignments:
        claim = claims.get(alignment.claim_id)
        if claim is None:
            continue
        expected_text = (
            claim.subject_text if alignment.entity_role == "subject" else claim.object_text
        )
        expected_normalized = (
            claim.normalized_subject
            if alignment.entity_role == "subject"
            else claim.normalized_object
        )
        if alignment.entity_text != expected_text or alignment.normalized_entity != expected_normalized:
            errors.append(
                f"Alignment for {(alignment.claim_id, alignment.entity_role)!r} "
                "does not match its claim entity"
            )
        if set(alignment.evidence_ids) != set(claim.evidence_ids):
            errors.append(
                f"Alignment for {(alignment.claim_id, alignment.entity_role)!r} "
                "does not preserve claim evidence"
            )
        if alignment.object_id is not None and alignment.object_id not in object_ids:
            errors.append(
                f"Alignment for {(alignment.claim_id, alignment.entity_role)!r} "
                f"references unknown object {alignment.object_id!r}"
            )
    if errors:
        raise ValueError("; ".join(errors))


def _confidence_for(*values: Confidence) -> Confidence:
    order = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
    return min(values, key=order.__getitem__) if values else "unknown"


def _comparison_outcome(
    consistent: bool,
    confidence: Confidence,
    *,
    low_confidence_reason: str,
) -> dict[str, object]:
    """Apply the shared status/severity policy without overstating weak evidence."""

    if consistent:
        return {"status": "confirmed_consistent", "severity": "info"}
    if confidence in {"high", "medium"}:
        return {"status": "confirmed_contradiction", "severity": "error"}
    return {
        "status": "probable_contradiction",
        "severity": "warning",
        "uncertainty": low_confidence_reason,
    }


class _FindingBuilder:
    def __init__(self) -> None:
        self.findings: list[ConsistencyFinding] = []

    def add(self, **values: object) -> None:
        values["id"] = f"finding-{len(self.findings) + 1:04d}"
        self.findings.append(ConsistencyFinding.model_validate(values))


def _diagram_internal_findings(diagram: AnalyzedDiagram, builder: _FindingBuilder) -> None:
    objects = {item.id: item for item in diagram.objects}
    references: dict[str, list[AnalyzedObject]] = {}
    for item in diagram.objects:
        for reference in item.reference_numbers:
            references.setdefault(reference.casefold(), []).append(item)
    for reference, matched in references.items():
        if len(matched) > 1:
            builder.add(
                category="duplicate_reference",
                status="diagram_internal_warning",
                severity="warning",
                diagram_fact=ComparisonProposition(
                    subject=reference,
                    predicate="assigned_to_multiple_objects",
                    object_or_value=", ".join(item.id for item in matched),
                ),
                diagram_evidence_ids=list(
                    dict.fromkeys(eid for item in matched for eid in item.evidence_ids)
                ),
                explanation=f"Reference {reference!r} is assigned to multiple visible objects.",
                confidence=_confidence_for(*(item.confidence for item in matched)),
                review_action="Verify the reference numeral assignments in the source diagram.",
            )

    participants: set[str] = set()
    for relationship in diagram.relationships:
        participants.update(
            item for item in (relationship.source_id, relationship.target_id) if item is not None
        )
        if "dangling" in {relationship.source_certainty, relationship.target_certainty}:
            builder.add(
                category="dangling_connector",
                status="diagram_internal_warning",
                severity="warning",
                diagram_fact=_relationship_fact(relationship, objects),
                diagram_evidence_ids=relationship.evidence_ids,
                explanation="A visible connector has at least one dangling endpoint.",
                confidence=relationship.confidence,
                review_action="Inspect both connector endpoints and confirm whether one is detached.",
            )
        if relationship.direction == "unclear":
            builder.add(
                category="ambiguous_direction",
                status="diagram_internal_warning",
                severity="warning",
                diagram_fact=_relationship_fact(relationship, objects),
                diagram_evidence_ids=relationship.evidence_ids,
                explanation="The connector is visible but its direction cannot be established.",
                confidence=relationship.confidence,
                review_action="Inspect the original-resolution arrowhead before relying on direction.",
            )

    for item in diagram.objects:
        if item.parent_id is not None:
            parent = objects.get(item.parent_id)
            if parent is not None and not _contains(parent, item):
                builder.add(
                    category="container_geometry",
                    status="diagram_internal_warning",
                    severity="warning",
                    diagram_fact=ComparisonProposition(
                        subject=item.normalized_label or item.id,
                        predicate="visibly_contained_by",
                        object_or_value=parent.normalized_label or parent.id,
                    ),
                    diagram_evidence_ids=list(
                        dict.fromkeys([*item.evidence_ids, *parent.evidence_ids])
                    ),
                    explanation="The interpreted child is not geometrically inside its labeled parent.",
                    confidence=_confidence_for(item.confidence, parent.confidence),
                    review_action="Confirm the intended containment boundary in the diagram.",
                )
        if diagram.relationships and item.id not in participants:
            builder.add(
                category="isolated_object",
                status="diagram_internal_warning",
                severity="warning",
                diagram_fact=_object_fact(item, "isolated"),
                diagram_evidence_ids=item.evidence_ids,
                explanation="The object is isolated while other diagram objects participate in connectors.",
                confidence=item.confidence,
                review_action="Check whether a faint, occluded, or missing connector should attach here.",
            )


def _resolved_object(
    claim_id: str,
    role: str,
    alignment_map: dict[tuple[str, str], EntityAlignment],
    objects: dict[str, AnalyzedObject],
) -> tuple[AnalyzedObject | None, EntityAlignment | None]:
    alignment = alignment_map.get((claim_id, role))
    if alignment is None or alignment.object_id is None:
        return None, alignment
    return objects.get(alignment.object_id), alignment


def _unverifiable(
    builder: _FindingBuilder,
    claim: DocumentClaim,
    diagram: AnalyzedDiagram,
    category: FindingCategory,
    reason: str,
) -> None:
    evidence = list(dict.fromkeys(eid for item in diagram.objects for eid in item.evidence_ids))
    if not evidence:
        evidence = [eid for item in diagram.relationships for eid in item.evidence_ids]
    builder.add(
        category=category,
        status="unverifiable",
        severity="warning",
        diagram_fact=ComparisonProposition(
            subject=claim.normalized_subject,
            predicate="not_verified",
            object_or_value=claim.normalized_object,
        ),
        text_claim=_claim_proposition(claim),
        claim_id=claim.id,
        diagram_evidence_ids=evidence,
        text_evidence_ids=claim.evidence_ids,
        explanation=reason,
        confidence="unknown",
        uncertainty=reason,
        review_action="Inspect the cited diagram region and prose before deciding whether they conflict.",
    )


def _compare_existence(
    builder: _FindingBuilder,
    claim: DocumentClaim,
    item: AnalyzedObject | None,
    diagram: AnalyzedDiagram,
) -> None:
    positive = claim.predicate == "exists" and claim.modality != "negated"
    if item is None:
        _unverifiable(
            builder,
            claim,
            diagram,
            "object_existence",
            "The claimed entity could not be aligned uniquely; absence cannot be proven from that alone.",
        )
        return
    contradiction = not positive
    confidence = _confidence_for(claim.confidence, item.confidence)
    builder.add(
        category="object_existence",
        **_comparison_outcome(
            not contradiction,
            confidence,
            low_confidence_reason="The reconstructed object has low or unknown confidence.",
        ),
        diagram_fact=_object_fact(item),
        text_claim=_claim_proposition(claim),
        claim_id=claim.id,
        diagram_evidence_ids=item.evidence_ids,
        text_evidence_ids=claim.evidence_ids,
        explanation=(
            "The diagram visibly contains an object that the prose says is absent."
            if contradiction
            else "The claimed object is present in the diagram."
        ),
        confidence=confidence,
        review_action="Verify the cited object and prose; neither source is assumed authoritative.",
    )


def _find_connecting_relationships(
    source: AnalyzedObject,
    target: AnalyzedObject,
    relationships: list[AnalyzedRelationship],
) -> list[AnalyzedRelationship]:
    endpoints = {source.id, target.id}
    return [
        item
        for item in relationships
        if item.source_id is not None
        and item.target_id is not None
        and {item.source_id, item.target_id} == endpoints
    ]


def _directed_state(
    relationship: AnalyzedRelationship,
    source: AnalyzedObject,
    target: AnalyzedObject,
) -> Literal["forward", "reverse", "bidirectional", "ambiguous"]:
    if relationship.direction in {"none", "unclear"}:
        return "ambiguous"
    if relationship.direction == "bidirectional":
        return "bidirectional"
    endpoints_match = relationship.source_id == source.id and relationship.target_id == target.id
    if relationship.direction == "forward":
        return "forward" if endpoints_match else "reverse"
    return "reverse" if endpoints_match else "forward"


def _compare_alignment_label(
    builder: _FindingBuilder,
    claim: DocumentClaim,
    item: AnalyzedObject | None,
    alignment: EntityAlignment | None,
) -> bool:
    """Report identity-supported label differences; return whether they are decisive."""

    if item is None or alignment is None or item.normalized_label is None:
        return False
    if alignment.normalized_entity == item.normalized_label:
        return False
    if alignment.method == "exact_reference":
        confidence = _confidence_for(claim.confidence, item.confidence)
        builder.add(
            category="label",
            **_comparison_outcome(
                False,
                confidence,
                low_confidence_reason="The identity is reference-supported, but the visible label evidence is weak.",
            ),
            diagram_fact=ComparisonProposition(
                subject=item.normalized_label,
                predicate="visible_label",
                object_or_value=", ".join(item.reference_numbers) or None,
            ),
            text_claim=_claim_proposition(claim),
            claim_id=claim.id,
            diagram_evidence_ids=item.evidence_ids,
            text_evidence_ids=claim.evidence_ids,
            explanation="The reference numeral identifies the same object, but its visible label differs from the prose.",
            confidence=confidence,
            review_action="Compare the label attached to the shared reference numeral in both sources.",
        )
        return True
    if alignment.method in {"conservative_fuzzy", "model_assisted", "explicit_alias"}:
        builder.add(
            category="alias" if alignment.method == "explicit_alias" else "terminology",
            status="terminology_difference",
            severity="info",
            diagram_fact=ComparisonProposition(
                subject=item.normalized_label,
                predicate="visible_label",
            ),
            text_claim=_claim_proposition(claim),
            claim_id=claim.id,
            diagram_evidence_ids=item.evidence_ids,
            text_evidence_ids=claim.evidence_ids,
            explanation="The aligned entity uses different wording in the diagram and prose.",
            confidence=_confidence_for(claim.confidence, item.confidence),
            review_action="Confirm that the two labels are intended to name the same component.",
        )
    return False


def _compare_binary_claim(
    builder: _FindingBuilder,
    claim: DocumentClaim,
    source: AnalyzedObject | None,
    target: AnalyzedObject | None,
    diagram: AnalyzedDiagram,
) -> None:
    category: FindingCategory = "sequence" if claim.predicate == "sequence" else "relationship"
    if source is None or target is None:
        _unverifiable(builder, claim, diagram, category, "One or both claim entities are unresolved.")
        return
    relationships = _find_connecting_relationships(source, target, diagram.relationships)
    if claim.modality in {"possible", "example"}:
        evidence = (
            relationships[0].evidence_ids
            if relationships
            else [*source.evidence_ids, *target.evidence_ids]
        )
        builder.add(
            category=category,
            status="confirmed_consistent",
            severity="info",
            diagram_fact=ComparisonProposition(
                subject=source.normalized_label or source.id,
                predicate="connection_allowed_but_not_required",
                object_or_value=target.normalized_label or target.id,
            ),
            text_claim=_claim_proposition(claim),
            claim_id=claim.id,
            diagram_evidence_ids=evidence,
            text_evidence_ids=claim.evidence_ids,
            explanation="A possible or example relationship does not require a visible connector.",
            confidence=claim.confidence,
            review_action="No correction is implied; confirm only if the prose was intended as mandatory.",
        )
        return
    negated = claim.modality == "negated"
    if not relationships:
        if negated:
            builder.add(
                category="negation",
                status="confirmed_consistent",
                severity="info",
                diagram_fact=ComparisonProposition(
                    subject=source.normalized_label or source.id,
                    predicate="no_visible_connection_to",
                    object_or_value=target.normalized_label or target.id,
                ),
                text_claim=_claim_proposition(claim),
                claim_id=claim.id,
                diagram_evidence_ids=list(
                    dict.fromkeys([*source.evidence_ids, *target.evidence_ids])
                ),
                text_evidence_ids=claim.evidence_ids,
                explanation="No relationship was reconstructed between the objects named by the negated claim.",
                confidence=_confidence_for(claim.confidence, source.confidence, target.confidence),
                review_action="No action is required unless a faint connector may have been missed.",
            )
            return
        builder.add(
            category=category,
            status="probable_contradiction",
            severity="warning",
            diagram_fact=ComparisonProposition(
                subject=source.normalized_label or source.id,
                predicate="no_visible_connection_to",
                object_or_value=target.normalized_label or target.id,
            ),
            text_claim=_claim_proposition(claim),
            claim_id=claim.id,
            diagram_evidence_ids=list(dict.fromkeys([*source.evidence_ids, *target.evidence_ids])),
            text_evidence_ids=claim.evidence_ids,
            explanation="The prose claims a relationship, but none was reconstructed between the aligned objects.",
            confidence=_confidence_for(claim.confidence, source.confidence, target.confidence),
            uncertainty="A faint, occluded, or unrecognized connector could account for the absence.",
            review_action="Inspect the space between the cited objects for an overlooked connector.",
        )
        return
    relationship = relationships[0]
    if negated:
        confidence = _confidence_for(claim.confidence, relationship.confidence)
        builder.add(
            category="negation",
            **_comparison_outcome(
                False,
                confidence,
                low_confidence_reason="The apparent relationship has low or unknown confidence.",
            ),
            diagram_fact=_relationship_fact(
                relationship, {item.id: item for item in diagram.objects}
            ),
            text_claim=_claim_proposition(claim),
            claim_id=claim.id,
            diagram_evidence_ids=relationship.evidence_ids,
            text_evidence_ids=claim.evidence_ids,
            explanation="A visible relationship contradicts the prose's negated relationship claim.",
            confidence=confidence,
            review_action="Verify the connector and negated prose; neither source is assumed authoritative.",
        )
        return
    if claim.predicate == "sequence":
        state = _directed_state(relationship, source, target)
        if state == "ambiguous":
            _unverifiable(builder, claim, diagram, "sequence", "Connector direction is visibly unclear.")
            return
        if state == "reverse":
            confidence = _confidence_for(claim.confidence, relationship.confidence)
            builder.add(
                category="sequence",
                **_comparison_outcome(
                    False,
                    confidence,
                    low_confidence_reason="The reconstructed arrow direction has low confidence.",
                ),
                diagram_fact=_relationship_fact(
                    relationship, {item.id: item for item in diagram.objects}
                ),
                text_claim=_claim_proposition(claim),
                claim_id=claim.id,
                diagram_evidence_ids=relationship.evidence_ids,
                text_evidence_ids=claim.evidence_ids,
                explanation="The visible connector orders the aligned objects opposite to the prose.",
                confidence=confidence,
                review_action="Verify the arrowhead direction and stated sequence order.",
            )
            return
    builder.add(
        category=category,
        status="confirmed_consistent",
        severity="info",
        diagram_fact=_relationship_fact(relationship, {item.id: item for item in diagram.objects}),
        text_claim=_claim_proposition(claim),
        claim_id=claim.id,
        diagram_evidence_ids=relationship.evidence_ids,
        text_evidence_ids=claim.evidence_ids,
        explanation="The aligned objects have a visible relationship consistent with the claim.",
        confidence=_confidence_for(claim.confidence, relationship.confidence),
        review_action="No action is required unless the relationship semantics need domain review.",
    )


def _single_incident_relationship(
    item: AnalyzedObject,
    diagram: AnalyzedDiagram,
) -> AnalyzedRelationship | None:
    matches = [
        relationship
        for relationship in diagram.relationships
        if item.id in {relationship.source_id, relationship.target_id}
    ]
    return matches[0] if len(matches) == 1 else None


def _compare_reference_mapping(
    builder: _FindingBuilder,
    claim: DocumentClaim,
    subject: AnalyzedObject | None,
    diagram: AnalyzedDiagram,
) -> None:
    if subject is None or claim.normalized_object is None:
        _unverifiable(builder, claim, diagram, "reference_number", "The referenced object or numeral is unresolved.")
        return
    expected = claim.normalized_object
    actual = [normalize_claim_text(value) for value in subject.reference_numbers]
    consistent = expected in actual
    confidence = _confidence_for(claim.confidence, subject.confidence)
    builder.add(
        category="reference_number",
        **_comparison_outcome(
            consistent,
            confidence,
            low_confidence_reason="The visible reference numeral has low or unknown confidence.",
        ),
        diagram_fact=ComparisonProposition(
            subject=subject.normalized_label or subject.id,
            predicate="reference_mapping",
            object_or_value=", ".join(actual) if actual else "no visible reference",
        ),
        text_claim=_claim_proposition(claim),
        claim_id=claim.id,
        diagram_evidence_ids=subject.evidence_ids,
        text_evidence_ids=claim.evidence_ids,
        explanation=(
            "The visible reference numeral matches the prose."
            if consistent
            else "The object's visible reference numeral differs from the prose."
        ),
        confidence=confidence,
        review_action="Compare the object's reference numeral in the diagram and prose.",
    )


def _compare_relationship_attribute(
    builder: _FindingBuilder,
    claim: DocumentClaim,
    subject: AnalyzedObject | None,
    diagram: AnalyzedDiagram,
) -> None:
    category: FindingCategory = (
        "direction" if claim.predicate == "direction" else "relationship_type"
    )
    if subject is None:
        _unverifiable(builder, claim, diagram, category, "The relationship subject is unresolved.")
        return
    relationship = _single_incident_relationship(subject, diagram)
    if relationship is None or claim.normalized_object is None:
        _unverifiable(
            builder,
            claim,
            diagram,
            category,
            "The subject does not identify exactly one relationship with a comparable value.",
        )
        return
    if claim.predicate == "relationship_type":
        actual = normalize_claim_text(relationship.relation)
        expected = claim.normalized_object
    else:
        if relationship.direction == "unclear":
            _unverifiable(builder, claim, diagram, "direction", "Connector direction is visibly unclear.")
            return
        supported_direction_values = {
            "forward",
            "reverse",
            "bidirectional",
            "none",
            "unclear",
        }
        if claim.normalized_object not in supported_direction_values:
            _unverifiable(
                builder,
                claim,
                diagram,
                "direction",
                f"{claim.normalized_object!r} is not a supported connector-direction value.",
            )
            return
        actual = normalize_claim_text(relationship.direction)
        expected = claim.normalized_object
    consistent = actual == expected
    confidence = _confidence_for(claim.confidence, relationship.confidence)
    builder.add(
        category=category,
        **_comparison_outcome(
            consistent,
            confidence,
            low_confidence_reason=f"The reconstructed {category.replace('_', ' ')} has low confidence.",
        ),
        diagram_fact=ComparisonProposition(
            subject=subject.normalized_label or subject.id,
            predicate=claim.predicate,
            object_or_value=actual,
        ),
        text_claim=_claim_proposition(claim),
        claim_id=claim.id,
        diagram_evidence_ids=relationship.evidence_ids,
        text_evidence_ids=claim.evidence_ids,
        explanation=(
            f"The visible {category.replace('_', ' ')} matches the prose."
            if consistent
            else f"The visible {category.replace('_', ' ')} differs from the prose."
        ),
        confidence=confidence,
        review_action=f"Verify the connector's {category.replace('_', ' ')} in both sources.",
    )


def _compare_cardinality(
    builder: _FindingBuilder,
    claim: DocumentClaim,
    subject: AnalyzedObject | None,
    diagram: AnalyzedDiagram,
) -> None:
    if subject is None or claim.normalized_object is None:
        _unverifiable(builder, claim, diagram, "cardinality", "The cardinality subject or value is unresolved.")
        return
    try:
        expected = int(claim.normalized_object)
    except ValueError:
        _unverifiable(builder, claim, diagram, "cardinality", "The cardinality value is not an exact integer.")
        return
    incident = [
        item
        for item in diagram.relationships
        if subject.id in {item.source_id, item.target_id}
    ]
    actual = len(incident)
    consistent = actual == expected
    confidence = _confidence_for(claim.confidence, subject.confidence)
    evidence = list(
        dict.fromkeys(
            [*subject.evidence_ids, *(eid for item in incident for eid in item.evidence_ids)]
        )
    )
    builder.add(
        category="cardinality",
        **_comparison_outcome(
            consistent,
            confidence,
            low_confidence_reason="The object or connector evidence has low confidence.",
        ),
        diagram_fact=ComparisonProposition(
            subject=subject.normalized_label or subject.id,
            predicate="connection_cardinality",
            object_or_value=str(actual),
        ),
        text_claim=_claim_proposition(claim),
        claim_id=claim.id,
        diagram_evidence_ids=evidence,
        text_evidence_ids=claim.evidence_ids,
        explanation=(
            "The visible connection count matches the prose."
            if consistent
            else "The visible connection count differs from the prose."
        ),
        confidence=confidence,
        review_action="Count the connectors incident to the cited object in the source diagram.",
    )


def _compare_claims(
    diagram: AnalyzedDiagram,
    batch: DocumentClaimBatch,
    alignments: EntityAlignmentSet,
    builder: _FindingBuilder,
) -> None:
    objects = {item.id: item for item in diagram.objects}
    alignment_map = _alignment_map(alignments)
    for claim in batch.claims:
        if claim.refers_to_candidate != "yes":
            continue
        subject, subject_alignment = _resolved_object(
            claim.id, "subject", alignment_map, objects
        )
        target, _ = _resolved_object(claim.id, "object", alignment_map, objects)
        decisive_label_mismatch = _compare_alignment_label(
            builder, claim, subject, subject_alignment
        )
        if claim.modality == "unknown":
            _unverifiable(builder, claim, diagram, "unsupported_claim", "Claim modality is unknown.")
        elif claim.predicate in {"exists", "not_exists"}:
            if not decisive_label_mismatch:
                _compare_existence(builder, claim, subject, diagram)
        elif claim.predicate in {"connects_to", "sequence"}:
            _compare_binary_claim(builder, claim, subject, target, diagram)
        elif claim.predicate == "reference_mapping":
            _compare_reference_mapping(builder, claim, subject, diagram)
        elif claim.predicate in {"direction", "relationship_type"}:
            _compare_relationship_attribute(builder, claim, subject, diagram)
        elif claim.predicate == "cardinality":
            _compare_cardinality(builder, claim, subject, diagram)
        elif claim.predicate == "type_or_role" and subject is not None:
            expected = claim.normalized_object or ""
            actual = normalize_claim_text(subject.semantic_type)
            contradiction = actual != expected
            builder.add(
                category="label" if not expected else "terminology",
                status="terminology_difference" if contradiction else "confirmed_consistent",
                severity="info",
                diagram_fact=_object_fact(subject, "type_or_role"),
                text_claim=_claim_proposition(claim),
                claim_id=claim.id,
                diagram_evidence_ids=subject.evidence_ids,
                text_evidence_ids=claim.evidence_ids,
                explanation=(
                    "The visible object type and prose terminology differ and may be synonymous."
                    if contradiction
                    else "The object role matches the document claim."
                ),
                confidence=_confidence_for(claim.confidence, subject.confidence),
                review_action="Confirm whether the two domain terms are equivalent.",
            )
        elif claim.predicate == "contains":
            if subject is None or target is None:
                _unverifiable(builder, claim, diagram, "containment", "A containment entity is unresolved.")
                continue
            consistent = target.parent_id == subject.id
            confidence = _confidence_for(
                claim.confidence, subject.confidence, target.confidence
            )
            builder.add(
                category="containment",
                **_comparison_outcome(
                    consistent,
                    confidence,
                    low_confidence_reason="The interpreted containment has low confidence.",
                ),
                diagram_fact=ComparisonProposition(
                    subject=target.normalized_label or target.id,
                    predicate="contained_by",
                    object_or_value=(
                        objects[target.parent_id].normalized_label or target.parent_id
                        if target.parent_id in objects
                        else "no_interpreted_parent"
                    ),
                ),
                text_claim=_claim_proposition(claim),
                claim_id=claim.id,
                diagram_evidence_ids=list(
                    dict.fromkeys([*subject.evidence_ids, *target.evidence_ids])
                ),
                text_evidence_ids=claim.evidence_ids,
                explanation=(
                    "The diagram containment matches the prose."
                    if consistent
                    else "The aligned child is not contained by the object named in the prose."
                ),
                confidence=confidence,
                review_action="Verify the cited container boundary and textual containment claim.",
            )
        elif claim.predicate == "figure_title":
            expected = claim.normalized_object or claim.normalized_subject
            actual = normalize_claim_text(diagram.title or "")
            if not diagram.title_evidence_ids:
                _unverifiable(builder, claim, diagram, "title", "No visible diagram title was reconstructed.")
                continue
            consistent = actual == expected
            confidence = _confidence_for(claim.confidence, diagram.confidence)
            builder.add(
                category="title",
                **_comparison_outcome(
                    consistent,
                    confidence,
                    low_confidence_reason="The visible title has low or unknown confidence.",
                ),
                diagram_fact=ComparisonProposition(subject=actual, predicate="figure_title"),
                text_claim=_claim_proposition(claim),
                claim_id=claim.id,
                diagram_evidence_ids=diagram.title_evidence_ids,
                text_evidence_ids=claim.evidence_ids,
                explanation="The visible title matches the claim." if consistent else "The visible title differs from the claim.",
                confidence=confidence,
                review_action="Compare the visible title with the cited caption or prose.",
            )
        elif claim.predicate == "alias":
            if subject is not None and target is not None and subject.id == target.id:
                builder.add(
                    category="alias",
                    status="confirmed_consistent",
                    severity="info",
                    diagram_fact=_object_fact(subject),
                    text_claim=_claim_proposition(claim),
                    claim_id=claim.id,
                    diagram_evidence_ids=subject.evidence_ids,
                    text_evidence_ids=claim.evidence_ids,
                    explanation="Both alias terms resolve to the same diagram object.",
                    confidence=_confidence_for(claim.confidence, subject.confidence),
                    review_action="No action is required unless the alias is domain-sensitive.",
                )
            else:
                _unverifiable(builder, claim, diagram, "terminology", "The alias terms do not resolve to one object.")
        else:
            _unverifiable(
                builder,
                claim,
                diagram,
                "unsupported_claim",
                f"Predicate {claim.predicate!r} requires semantic adjudication not performed by deterministic rules.",
            )


def _validate_finding_references(
    analysis: ConsistencyAnalysis,
    diagram: AnalyzedDiagram,
    batch: DocumentClaimBatch,
) -> None:
    diagram_evidence = set(diagram.title_evidence_ids)
    for collection in (
        diagram.objects,
        diagram.relationships,
        diagram.groups,
        diagram.legends,
        diagram.annotations,
    ):
        for item in collection:
            diagram_evidence.update(item.evidence_ids)
    text_evidence = {item.id for item in batch.evidence}
    claims = {item.id for item in batch.claims}
    errors: list[str] = []
    for finding in analysis.findings:
        unknown_diagram = set(finding.diagram_evidence_ids) - diagram_evidence
        unknown_text = set(finding.text_evidence_ids) - text_evidence
        if unknown_diagram:
            errors.append(f"{finding.id} cites unknown diagram evidence {sorted(unknown_diagram)}")
        if unknown_text:
            errors.append(f"{finding.id} cites unknown text evidence {sorted(unknown_text)}")
        if finding.claim_id is not None and finding.claim_id not in claims:
            errors.append(f"{finding.id} cites unknown claim {finding.claim_id!r}")
    if errors:
        raise ValueError("; ".join(errors))


def compare_diagram_and_claims(
    diagram: AnalyzedDiagram,
    batch: DocumentClaimBatch,
    alignments: EntityAlignmentSet,
    *,
    strict_coverage: bool = False,
) -> ConsistencyAnalysis:
    """Run conservative deterministic A6 checks and validate all finding evidence."""

    candidate_ids = {diagram.candidate_id, batch.candidate_id, alignments.candidate_id}
    if len(candidate_ids) != 1:
        raise ValueError("Diagram, claim batch, and alignments must share a candidate ID")
    _validate_alignment_references(diagram, batch, alignments)
    builder = _FindingBuilder()
    _diagram_internal_findings(diagram, builder)
    _compare_claims(diagram, batch, alignments, builder)

    # Strict coverage is intentionally inert without evidence-bearing exhaustive
    # claims. A user policy alone cannot manufacture a text citation.
    exhaustive_object_claims = [
        claim for claim in batch.claims if claim.exhaustive and claim.predicate == "exists"
    ]
    aligned_objects = {
        item.object_id
        for item in alignments.alignments
        if item.object_id is not None
        and any(claim.id == item.claim_id for claim in exhaustive_object_claims)
    }
    if exhaustive_object_claims:
        anchor = exhaustive_object_claims[0]
        for item in diagram.objects:
            if item.id not in aligned_objects:
                builder.add(
                    category="exhaustive_scope",
                    status="possible_omission",
                    severity="warning",
                    diagram_fact=_object_fact(item),
                    text_claim=_claim_proposition(anchor),
                    claim_id=anchor.id,
                    diagram_evidence_ids=item.evidence_ids,
                    text_evidence_ids=anchor.evidence_ids,
                    explanation="The visible object is not represented in the exhaustive textual inventory.",
                    confidence=_confidence_for(item.confidence, anchor.confidence),
                    review_action="Determine whether the inventory or diagram should include this component.",
                )

    exhaustive_relationship_claims = [
        claim
        for claim in batch.claims
        if claim.exhaustive and claim.predicate in {"connects_to", "sequence"}
    ]
    if exhaustive_relationship_claims:
        alignment_map = _alignment_map(alignments)
        represented: set[frozenset[str]] = set()
        for claim in exhaustive_relationship_claims:
            subject, _ = _resolved_object(claim.id, "subject", alignment_map, {
                item.id: item for item in diagram.objects
            })
            target, _ = _resolved_object(claim.id, "object", alignment_map, {
                item.id: item for item in diagram.objects
            })
            if subject is not None and target is not None:
                represented.add(frozenset((subject.id, target.id)))
        anchor = exhaustive_relationship_claims[0]
        objects = {item.id: item for item in diagram.objects}
        for relationship in diagram.relationships:
            endpoints = frozenset(
                item
                for item in (relationship.source_id, relationship.target_id)
                if item is not None
            )
            if len(endpoints) == 2 and endpoints not in represented:
                builder.add(
                    category="exhaustive_scope",
                    status="possible_omission",
                    severity="warning",
                    diagram_fact=_relationship_fact(relationship, objects),
                    text_claim=_claim_proposition(anchor),
                    claim_id=anchor.id,
                    diagram_evidence_ids=relationship.evidence_ids,
                    text_evidence_ids=anchor.evidence_ids,
                    explanation=(
                        "The visible relationship is not represented in the exhaustive "
                        "textual relationship inventory."
                    ),
                    confidence=_confidence_for(relationship.confidence, anchor.confidence),
                    review_action=(
                        "Determine whether the relationship inventory or diagram should "
                        "include this connection."
                    ),
                )

    analysis = ConsistencyAnalysis(
        candidate_id=diagram.candidate_id,
        strict_coverage=strict_coverage,
        findings=builder.findings,
    )
    _validate_finding_references(analysis, diagram, batch)
    return analysis


def summarize_finding_statuses(analysis: ConsistencyAnalysis) -> dict[str, int]:
    """Return stable report counts without hiding zero-result analyses."""

    return dict(sorted(Counter(item.status for item in analysis.findings).items()))


def render_findings_markdown(analysis: ConsistencyAnalysis) -> str:
    """Render an evidence-explicit human review section for an A6 result."""

    lines = ["## Consistency findings", ""]
    if not analysis.findings:
        return "\n".join([*lines, "No reportable consistency findings were produced.", ""])
    for finding in analysis.findings:
        lines.extend(
            [
                f"### {finding.id}: {finding.category}",
                "",
                f"- Status: `{finding.status}`",
                f"- Severity: `{finding.severity}`",
                f"- Confidence: `{finding.confidence}`",
                f"- Diagram evidence: {', '.join(finding.diagram_evidence_ids)}",
                f"- Text evidence: {', '.join(finding.text_evidence_ids) or 'not applicable'}",
                f"- Explanation: {finding.explanation}",
                f"- Review action: {finding.review_action}",
            ]
        )
        if finding.uncertainty:
            lines.append(f"- Uncertainty: {finding.uncertainty}")
        lines.append("")
    return "\n".join(lines)
