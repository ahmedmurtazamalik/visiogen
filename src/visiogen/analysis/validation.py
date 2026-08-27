"""Hard A3 evidence, coordinate, label, and cross-reference validation."""

from __future__ import annotations

import re

from visiogen.analysis.models import PreparedCandidate
from visiogen.analysis.semantics import (
    AnalyzedDiagram,
    NormalizedPoint,
    RawObservationBatch,
    ValidatedObservationSet,
    VisualEvidence,
    VisualObservation,
)
from visiogen.documents.models import NormalizedBox


class AnalysisValidationError(ValueError):
    """Schema-valid model output violated hard visual-evidence invariants."""

    def __init__(self, findings: list[str]) -> None:
        self.findings = tuple(findings)
        super().__init__("; ".join(findings))


def normalize_visible_text(value: str) -> str:
    """Conservative comparison normalization that never changes stored visible text."""

    return " ".join(value.casefold().split())


def _transform_box(local: NormalizedBox, source: NormalizedBox) -> NormalizedBox:
    width = source.right - source.left
    height = source.bottom - source.top
    return NormalizedBox(
        left=source.left + local.left * width,
        top=source.top + local.top * height,
        right=source.left + local.right * width,
        bottom=source.top + local.bottom * height,
    )


def _transform_point(point: NormalizedPoint, source: NormalizedBox) -> NormalizedPoint:
    return NormalizedPoint(
        x=source.left + point.x * (source.right - source.left),
        y=source.top + point.y * (source.bottom - source.top),
    )


def validate_observations(
    batch: RawObservationBatch,
    prepared: PreparedCandidate,
) -> ValidatedObservationSet:
    """Resolve derivative references and transform local evidence to source coordinates."""

    findings: list[str] = []
    if batch.candidate_id != prepared.candidate_id:
        findings.append("Observation candidate_id does not match the prepared candidate")
    derivatives = {item.id: item for item in prepared.derivatives}
    evidence_ids = [item.id for item in batch.evidence]
    observation_ids = [item.id for item in batch.observations]
    if len(evidence_ids) != len(set(evidence_ids)):
        findings.append("Observation evidence IDs must be unique")
    if len(observation_ids) != len(set(observation_ids)):
        findings.append("Visual observation IDs must be unique")
    known_evidence = set(evidence_ids)
    raw_evidence = {item.id: item for item in batch.evidence}
    for evidence in batch.evidence:
        if evidence.derivative_id not in derivatives:
            findings.append(
                f"Evidence '{evidence.id}' references unknown derivative "
                f"'{evidence.derivative_id}'"
            )
    for observation in batch.observations:
        if observation.geometry_derivative_id not in derivatives:
            findings.append(
                f"Observation '{observation.id}' references unknown geometry derivative "
                f"'{observation.geometry_derivative_id}'"
            )
        for evidence_id in observation.evidence_ids:
            if evidence_id not in known_evidence:
                findings.append(
                    f"Observation '{observation.id}' references unknown evidence "
                    f"'{evidence_id}'"
                )
        if not any(
            raw_evidence[evidence_id].derivative_id == observation.geometry_derivative_id
            for evidence_id in observation.evidence_ids
            if evidence_id in raw_evidence
        ):
            findings.append(
                f"Observation '{observation.id}' has no evidence on its geometry derivative"
            )
    if findings:
        raise AnalysisValidationError(findings)
    evidence = [
        VisualEvidence(
            id=item.id,
            derivative_id=item.derivative_id,
            local_bbox=item.local_bbox,
            source_bbox=_transform_box(
                item.local_bbox,
                derivatives[item.derivative_id].source_region,
            ),
        )
        for item in batch.evidence
    ]
    transformed_observations = [
        VisualObservation(
            id=item.id,
            kind=item.kind,
            source_bbox=(
                _transform_box(
                    item.local_bbox,
                    derivatives[item.geometry_derivative_id].source_region,
                )
                if item.local_bbox is not None
                else None
            ),
            source_path=[
                _transform_point(
                    point,
                    derivatives[item.geometry_derivative_id].source_region,
                )
                for point in item.local_path
            ],
            visible_text=item.visible_text,
            properties=item.properties,
            evidence_ids=item.evidence_ids,
            confidence=item.confidence,
            alternatives=item.alternatives,
        )
        for item in batch.observations
    ]
    return ValidatedObservationSet(
        candidate_id=batch.candidate_id,
        evidence=evidence,
        observations=transformed_observations,
        warnings=batch.warnings,
    )


def _text_for_evidence(
    observations: ValidatedObservationSet,
) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for observation in observations.observations:
        if observation.visible_text is None:
            continue
        for evidence_id in observation.evidence_ids:
            evidence_text = values.setdefault(evidence_id, [])
            if observation.visible_text not in evidence_text:
                evidence_text.append(observation.visible_text)
    return values


def _label_is_observed(
    label: str,
    evidence_ids: list[str],
    text_by_evidence: dict[str, list[str]],
) -> bool:
    normalized_label = normalize_visible_text(label)
    cited_text: list[str] = []
    for evidence_id in evidence_ids:
        for value in text_by_evidence.get(evidence_id, []):
            if normalize_visible_text(value) == normalized_label:
                return True
            if value not in cited_text:
                cited_text.append(value)
    return normalize_visible_text(" ".join(cited_text)) == normalized_label


def discard_unsupported_legends(
    diagram: AnalyzedDiagram,
    observations: ValidatedObservationSet,
) -> AnalyzedDiagram:
    """Omit inferred legend mappings while preserving an explicit audit limitation."""

    text_by_evidence = _text_for_evidence(observations)
    supported = [
        legend
        for legend in diagram.legends
        if _label_is_observed(legend.meaning, legend.evidence_ids, text_by_evidence)
    ]
    omitted = len(diagram.legends) - len(supported)
    if omitted == 0:
        return diagram
    noun = "mapping" if omitted == 1 else "mappings"
    limitation = (
        f"Omitted {omitted} legend {noun} whose meaning was not literally visible "
        "in cited evidence."
    )
    return diagram.model_copy(
        update={
            "legends": supported,
            "limitations": [*diagram.limitations, limitation],
        }
    )


def downgrade_unsupported_relationship_endpoints(
    diagram: AnalyzedDiagram,
) -> AnalyzedDiagram:
    """Preserve geometrically unsupported endpoint claims as explicit ambiguity."""

    objects_by_id = {item.id: item for item in diagram.objects}
    relationships = []
    downgraded = 0
    for relationship in diagram.relationships:
        updates: dict[str, str] = {}
        if len(relationship.path) >= 2:
            source = objects_by_id.get(relationship.source_id or "")
            if (
                source is not None
                and relationship.source_certainty == "known"
                and not _point_near_box(relationship.path[0], source.bbox)
            ):
                updates["source_certainty"] = "ambiguous"
            target = objects_by_id.get(relationship.target_id or "")
            if (
                target is not None
                and relationship.target_certainty == "known"
                and not _point_near_box(relationship.path[-1], target.bbox)
            ):
                updates["target_certainty"] = "ambiguous"
        if updates:
            downgraded += len(updates)
            relationship = relationship.model_copy(update=updates)
        relationships.append(relationship)
    if downgraded == 0:
        return diagram
    noun = "endpoint" if downgraded == 1 else "endpoints"
    limitation = (
        f"Downgraded {downgraded} relationship {noun} to ambiguous because the "
        "reconstructed path did not geometrically reach the claimed object."
    )
    return diagram.model_copy(
        update={
            "relationships": relationships,
            "limitations": [*diagram.limitations, limitation],
        }
    )


def _boxes_intersect(first: NormalizedBox, second: NormalizedBox) -> bool:
    return not (
        first.right <= second.left
        or second.right <= first.left
        or first.bottom <= second.top
        or second.bottom <= first.top
    )


def _point_near_box(point: NormalizedPoint, box: NormalizedBox, margin: float = 0.04) -> bool:
    return (
        box.left - margin <= point.x <= box.right + margin
        and box.top - margin <= point.y <= box.bottom + margin
    )


def _box_contains(outer: NormalizedBox, inner: NormalizedBox, margin: float = 0.01) -> bool:
    return (
        outer.left - margin <= inner.left
        and outer.top - margin <= inner.top
        and outer.right + margin >= inner.right
        and outer.bottom + margin >= inner.bottom
    )


def validate_analyzed_diagram(
    diagram: AnalyzedDiagram,
    observations: ValidatedObservationSet,
) -> AnalyzedDiagram:
    """Reject invented labels, unresolved references, cycles, and evidence gaps."""

    findings: list[str] = []
    if diagram.candidate_id != observations.candidate_id:
        findings.append("Analyzed diagram candidate_id does not match observations")
    object_ids = [item.id for item in diagram.objects]
    relationship_ids = [item.id for item in diagram.relationships]
    group_ids = [item.id for item in diagram.groups]
    annotation_ids = [item.id for item in diagram.annotations]
    for label, ids in (
        ("object", object_ids),
        ("relationship", relationship_ids),
        ("group", group_ids),
        ("annotation", annotation_ids),
    ):
        if len(ids) != len(set(ids)):
            findings.append(f"Analyzed {label} IDs must be unique")
    known_objects = set(object_ids)
    evidence_by_id = {item.id: item for item in observations.evidence}
    known_evidence = set(evidence_by_id)
    text_by_evidence = _text_for_evidence(observations)
    kinds_by_evidence: dict[str, set[str]] = {}
    for observation in observations.observations:
        for evidence_id in observation.evidence_ids:
            kinds_by_evidence.setdefault(evidence_id, set()).add(observation.kind)
    parents = {item.id: item.parent_id for item in diagram.objects}
    objects_by_id = {item.id: item for item in diagram.objects}

    for evidence_id in diagram.title_evidence_ids:
        if evidence_id not in known_evidence:
            findings.append(f"Diagram title references unknown evidence '{evidence_id}'")
    if diagram.title is not None and not _label_is_observed(
        diagram.title,
        diagram.title_evidence_ids,
        text_by_evidence,
    ):
        findings.append("Diagram title is not present in cited evidence")

    for item in diagram.objects:
        if item.parent_id is not None and item.parent_id not in known_objects:
            findings.append(f"Object '{item.id}' references unknown parent '{item.parent_id}'")
        elif item.parent_id is not None and not _box_contains(
            objects_by_id[item.parent_id].bbox,
            item.bbox,
        ):
            findings.append(
                f"Object '{item.id}' is not geometrically contained by parent "
                f"'{item.parent_id}'"
            )
        for evidence_id in item.evidence_ids:
            if evidence_id not in known_evidence:
                findings.append(f"Object '{item.id}' references unknown evidence '{evidence_id}'")
        if not any(
            _boxes_intersect(item.bbox, evidence_by_id[evidence_id].source_bbox)
            for evidence_id in item.evidence_ids
            if evidence_id in evidence_by_id
        ):
            findings.append(f"Object '{item.id}' does not intersect its cited evidence")
        if item.visible_label is not None:
            if item.normalized_label != normalize_visible_text(item.visible_label):
                findings.append(f"Object '{item.id}' has an invalid normalized label")
            if not _label_is_observed(item.visible_label, item.evidence_ids, text_by_evidence):
                findings.append(f"Object '{item.id}' label is not present in cited evidence")
        cited_text = " ".join(
            text
            for evidence_id in item.evidence_ids
            for text in text_by_evidence.get(evidence_id, set())
        )
        for reference in item.reference_numbers:
            if re.search(rf"(?<!\w){re.escape(reference)}(?!\w)", cited_text) is None:
                findings.append(
                    f"Object '{item.id}' reference number '{reference}' is not visibly evidenced"
                )

    for start in object_ids:
        seen: set[str] = set()
        current: str | None = start
        while current is not None and current in parents:
            if current in seen:
                findings.append(f"Object containment cycle includes '{current}'")
                break
            seen.add(current)
            current = parents[current]

    for relationship in diagram.relationships:
        for endpoint_name, endpoint in (
            ("source", relationship.source_id),
            ("target", relationship.target_id),
        ):
            if endpoint is not None and endpoint not in known_objects:
                findings.append(
                    f"Relationship '{relationship.id}' references unknown {endpoint_name} "
                    f"object '{endpoint}'"
                )
        for evidence_id in relationship.evidence_ids:
            if evidence_id not in known_evidence:
                findings.append(
                    f"Relationship '{relationship.id}' references unknown evidence '{evidence_id}'"
                )
        if not any(
            kinds_by_evidence.get(evidence_id, set()) & {"connector", "arrowhead"}
            for evidence_id in relationship.evidence_ids
        ):
            findings.append(
                f"Relationship '{relationship.id}' cites no connector or arrowhead observation"
            )
        if relationship.path and not any(
            _point_near_box(point, evidence_by_id[evidence_id].source_bbox, margin=0.06)
            for point in relationship.path
            for evidence_id in relationship.evidence_ids
            if evidence_id in evidence_by_id
        ):
            findings.append(
                f"Relationship '{relationship.id}' path is not near its cited evidence"
            )
        if relationship.visible_label is not None:
            if relationship.normalized_label != normalize_visible_text(
                relationship.visible_label
            ):
                findings.append(
                    f"Relationship '{relationship.id}' has an invalid normalized label"
                )
            if not _label_is_observed(
                relationship.visible_label,
                relationship.evidence_ids,
                text_by_evidence,
            ):
                findings.append(
                    f"Relationship '{relationship.id}' label is not present in cited evidence"
                )
        if len(relationship.path) >= 2:
            if relationship.source_id in parents and relationship.source_certainty == "known":
                source = next(item for item in diagram.objects if item.id == relationship.source_id)
                if not _point_near_box(relationship.path[0], source.bbox):
                    findings.append(
                        f"Relationship '{relationship.id}' path does not begin near its source"
                    )
            if relationship.target_id in parents and relationship.target_certainty == "known":
                target = next(item for item in diagram.objects if item.id == relationship.target_id)
                if not _point_near_box(relationship.path[-1], target.bbox):
                    findings.append(
                        f"Relationship '{relationship.id}' path does not end near its target"
                    )

    for group in diagram.groups:
        for object_id in group.object_ids:
            if object_id not in known_objects:
                findings.append(f"Group '{group.id}' references unknown object '{object_id}'")
        for evidence_id in group.evidence_ids:
            if evidence_id not in known_evidence:
                findings.append(f"Group '{group.id}' references unknown evidence '{evidence_id}'")
        if not any(
            _boxes_intersect(group.bbox, evidence_by_id[evidence_id].source_bbox)
            for evidence_id in group.evidence_ids
            if evidence_id in evidence_by_id
        ):
            findings.append(f"Group '{group.id}' does not intersect its cited evidence")
        for object_id in group.object_ids:
            if object_id in objects_by_id and not _boxes_intersect(
                group.bbox,
                objects_by_id[object_id].bbox,
            ):
                findings.append(
                    f"Group '{group.id}' does not intersect member object '{object_id}'"
                )
        if group.visible_label is not None and not _label_is_observed(
            group.visible_label,
            group.evidence_ids,
            text_by_evidence,
        ):
            findings.append(f"Group '{group.id}' label is not present in cited evidence")
    for legend in diagram.legends:
        for evidence_id in legend.evidence_ids:
            if evidence_id not in known_evidence:
                findings.append(f"Legend references unknown evidence '{evidence_id}'")
        if not _label_is_observed(
            legend.meaning,
            legend.evidence_ids,
            text_by_evidence,
        ):
            findings.append("Legend meaning is not present in cited evidence")
    for annotation in diagram.annotations:
        for object_id in annotation.attached_object_ids:
            if object_id not in known_objects:
                findings.append(
                    f"Annotation '{annotation.id}' references unknown object '{object_id}'"
                )
        for evidence_id in annotation.evidence_ids:
            if evidence_id not in known_evidence:
                findings.append(
                    f"Annotation '{annotation.id}' references unknown evidence '{evidence_id}'"
                )
        if not any(
            _boxes_intersect(annotation.bbox, evidence_by_id[evidence_id].source_bbox)
            for evidence_id in annotation.evidence_ids
            if evidence_id in evidence_by_id
        ):
            findings.append(
                f"Annotation '{annotation.id}' does not intersect its cited evidence"
            )
        if not _label_is_observed(
            annotation.visible_text,
            annotation.evidence_ids,
            text_by_evidence,
        ):
            findings.append(
                f"Annotation '{annotation.id}' text is not present in cited evidence"
            )
    if findings:
        raise AnalysisValidationError(findings)
    return diagram
