"""Exact A4 coverage scoring against a validated A3 semantic model."""

from __future__ import annotations

from pydantic import Field

from visiogen.analysis.description import (
    DiagramDescription,
    validate_diagram_description,
)
from visiogen.analysis.models import AnalysisModel
from visiogen.analysis.semantics import AnalyzedDiagram


class DescriptionCoverageScore(AnalysisModel):
    """Mechanically measured semantic and uncertainty coverage for one description."""

    candidate_id: str = Field(min_length=1)
    object_coverage: float = Field(ge=0, le=1)
    relationship_coverage: float = Field(ge=0, le=1)
    group_coverage: float = Field(ge=0, le=1)
    annotation_coverage: float = Field(ge=0, le=1)
    legend_coverage: float = Field(ge=0, le=1)
    limitation_coverage: float = Field(ge=0, le=1)
    visible_label_coverage: float = Field(ge=0, le=1)
    reference_number_coverage: float = Field(ge=0, le=1)
    ambiguity_coverage: float = Field(ge=0, le=1)
    canonical_sections: bool


def _ratio(matched: int, expected: int) -> float:
    return 1.0 if expected == 0 else matched / expected


def score_description_coverage(
    description: DiagramDescription,
    diagram: AnalyzedDiagram,
) -> DescriptionCoverageScore:
    """Score exact trace coverage after the hard A4 validator succeeds."""

    validate_diagram_description(description, diagram)
    statements = [item for section in description.sections for item in section.statements]
    object_ids = {value for item in statements for value in item.object_ids}
    relationship_ids = {value for item in statements for value in item.relationship_ids}
    group_ids = {value for item in statements for value in item.group_ids}
    annotation_ids = {value for item in statements for value in item.annotation_ids}
    legend_indices = {value for item in statements for value in item.legend_indices}
    limitation_indices = {value for item in statements for value in item.limitation_indices}
    visible_labels = [
        (item.id, item.visible_label, "object")
        for item in diagram.objects
        if item.visible_label is not None
    ] + [
        (item.id, item.visible_label, "relationship")
        for item in diagram.relationships
        if item.visible_label is not None
    ] + [
        (item.id, item.visible_label, "group")
        for item in diagram.groups
        if item.visible_label is not None
    ] + [
        (item.id, item.visible_text, "annotation")
        for item in diagram.annotations
    ]
    visible_label_matches = sum(
        any(
            label in statement.text
            and (
                (kind == "object" and item_id in statement.object_ids)
                or (kind == "relationship" and item_id in statement.relationship_ids)
                or (kind == "group" and item_id in statement.group_ids)
                or (kind == "annotation" and item_id in statement.annotation_ids)
            )
            for statement in statements
        )
        for item_id, label, kind in visible_labels
    )
    if diagram.title is not None:
        visible_labels.append((diagram.candidate_id, diagram.title, "title"))
        visible_label_matches += int(
            any(
                diagram.title in statement.text and statement.section == "identity"
                for statement in statements
            )
        )
    references = [
        (item.id, reference)
        for item in diagram.objects
        for reference in item.reference_numbers
    ]
    reference_matches = sum(
        any(
            reference in statement.text and item_id in statement.object_ids
            for statement in statements
        )
        for item_id, reference in references
    )
    ambiguous_objects = {
        item.id
        for item in diagram.objects
        if item.alternatives or item.confidence in {"low", "unknown"}
    }
    connected_ids = {
        value
        for relationship in diagram.relationships
        for value in (relationship.source_id, relationship.target_id)
        if value is not None
    }
    container_ids = {item.parent_id for item in diagram.objects if item.parent_id is not None}
    ambiguous_objects.update(
        item.id
        for item in diagram.objects
        if item.id not in connected_ids and item.id not in container_ids
    )
    ambiguous_relationships = {
        item.id
        for item in diagram.relationships
        if (
            item.direction == "unclear"
            or item.source_certainty != "known"
            or item.target_certainty != "known"
            or item.alternatives
            or item.confidence in {"low", "unknown"}
        )
    }
    ambiguous_annotations = {
        item.id
        for item in diagram.annotations
        if item.alternatives or item.confidence in {"low", "unknown"}
    }
    ambiguity_statements = [item for item in statements if item.section == "ambiguities"]
    ambiguity_matches = sum(
        any(item_id in statement.object_ids for statement in ambiguity_statements)
        for item_id in ambiguous_objects
    ) + sum(
        any(item_id in statement.relationship_ids for statement in ambiguity_statements)
        for item_id in ambiguous_relationships
    ) + sum(
        any(item_id in statement.annotation_ids for statement in ambiguity_statements)
        for item_id in ambiguous_annotations
    )
    ambiguity_total = (
        len(ambiguous_objects)
        + len(ambiguous_relationships)
        + len(ambiguous_annotations)
    )
    return DescriptionCoverageScore(
        candidate_id=diagram.candidate_id,
        object_coverage=_ratio(len(object_ids), len(diagram.objects)),
        relationship_coverage=_ratio(len(relationship_ids), len(diagram.relationships)),
        group_coverage=_ratio(len(group_ids), len(diagram.groups)),
        annotation_coverage=_ratio(len(annotation_ids), len(diagram.annotations)),
        legend_coverage=_ratio(len(legend_indices), len(diagram.legends)),
        limitation_coverage=_ratio(len(limitation_indices), len(diagram.limitations)),
        visible_label_coverage=_ratio(visible_label_matches, len(visible_labels)),
        reference_number_coverage=_ratio(reference_matches, len(references)),
        ambiguity_coverage=_ratio(ambiguity_matches, ambiguity_total),
        canonical_sections=len(description.sections) == 8,
    )
