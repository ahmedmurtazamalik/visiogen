"""Hard A3 evidence, coordinate, label, and cross-reference validation."""

from __future__ import annotations

import re
import unicodedata

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


def normalize_duplicate_observation_ids(batch: RawObservationBatch) -> RawObservationBatch:
    """Renumber duplicate observation IDs without changing visual evidence.

    Observation IDs are local mechanical identifiers and no other observation-stage
    record references them. Duplicate occurrences can therefore receive the next
    unused canonical ID while preserving their kind, geometry, text, properties,
    evidence references, confidence, and alternatives.
    """

    used: set[str] = set()
    next_number = 1
    observations = []
    changed = False
    for observation in batch.observations:
        observation_id = observation.id
        if observation_id in used:
            while f"observation-{next_number:04d}" in used:
                next_number += 1
            observation_id = f"observation-{next_number:04d}"
            next_number += 1
            observation = observation.model_copy(update={"id": observation_id})
            changed = True
        used.add(observation_id)
        observations.append(observation)
    if not changed:
        return batch
    return batch.model_copy(update={"observations": observations})


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


def _box_intersects_exact_text_observation(
    bbox: NormalizedBox,
    text: str,
    evidence_ids: list[str],
    observations: ValidatedObservationSet,
) -> bool:
    """Accept geometry anchored to an exact literal mark sharing cited evidence."""

    normalized = normalize_visible_text(text)
    cited = set(evidence_ids)
    return any(
        observation.source_bbox is not None
        and observation.visible_text is not None
        and normalize_visible_text(observation.visible_text) == normalized
        and cited.intersection(observation.evidence_ids)
        and _boxes_intersect(bbox, observation.source_bbox)
        for observation in observations.observations
    )


def _reference_is_observed(reference: str, cited_text: str) -> bool:
    if reference and all(unicodedata.category(char).startswith("N") for char in reference):
        start = 0
        while (index := cited_text.find(reference, start)) >= 0:
            before = cited_text[index - 1] if index > 0 else None
            after_index = index + len(reference)
            after = cited_text[after_index] if after_index < len(cited_text) else None
            if not (
                before is not None
                and unicodedata.category(before).startswith("N")
            ) and not (
                after is not None
                and unicodedata.category(after).startswith("N")
            ):
                return True
            start = index + 1
        return False
    return re.search(rf"(?<!\w){re.escape(reference)}(?!\w)", cited_text) is not None


def sanitize_object_grounding(
    diagram: AnalyzedDiagram,
    observations: ValidatedObservationSet,
    *,
    omit_unsupported: bool = False,
) -> AnalyzedDiagram:
    """Repair exact object-label citations and optionally omit unsupported object text."""

    text_by_evidence = _text_for_evidence(observations)
    objects = []
    regrounded_labels = 0
    omitted_labels = 0
    omitted_references = 0
    for item in diagram.objects:
        updates: dict[str, object] = {}
        evidence_ids = list(item.evidence_ids)
        if item.visible_label is not None and not _label_is_observed(
            item.visible_label,
            evidence_ids,
            text_by_evidence,
        ):
            matching_evidence = [
                evidence_id
                for evidence_id in text_by_evidence
                if _label_is_observed(
                    item.visible_label,
                    [evidence_id],
                    text_by_evidence,
                )
            ]
            if matching_evidence:
                evidence_ids.extend(
                    evidence_id
                    for evidence_id in matching_evidence
                    if evidence_id not in evidence_ids
                )
                updates["evidence_ids"] = evidence_ids
                regrounded_labels += 1
            elif omit_unsupported:
                updates["visible_label"] = None
                updates["normalized_label"] = None
                omitted_labels += 1
        if omit_unsupported and item.reference_numbers:
            cited_text = " ".join(
                text
                for evidence_id in evidence_ids
                for text in text_by_evidence.get(evidence_id, [])
            )
            supported_references = [
                reference
                for reference in item.reference_numbers
                if _reference_is_observed(reference, cited_text)
            ]
            omitted_references += len(item.reference_numbers) - len(supported_references)
            if supported_references != item.reference_numbers:
                updates["reference_numbers"] = supported_references
        objects.append(item.model_copy(update=updates) if updates else item)
    limitations = list(diagram.limitations)
    if regrounded_labels:
        noun = "label" if regrounded_labels == 1 else "labels"
        limitations.append(
            f"Re-grounded {regrounded_labels} object {noun} to exact visible-text evidence."
        )
    if omitted_labels:
        noun = "label" if omitted_labels == 1 else "labels"
        limitations.append(
            f"Omitted {omitted_labels} object {noun} not literally visible in observation "
            "evidence."
        )
    if omitted_references:
        noun = "number" if omitted_references == 1 else "numbers"
        limitations.append(
            f"Omitted {omitted_references} object reference {noun} not visibly evidenced."
        )
    if objects == diagram.objects and limitations == diagram.limitations:
        return diagram
    return diagram.model_copy(update={"objects": objects, "limitations": limitations})


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


def discard_unsupported_annotations(
    diagram: AnalyzedDiagram,
    observations: ValidatedObservationSet,
) -> AnalyzedDiagram:
    """Omit annotation text that is not literally grounded in cited observations."""

    text_by_evidence = _text_for_evidence(observations)
    supported = [
        annotation
        for annotation in diagram.annotations
        if _label_is_observed(
            annotation.visible_text,
            annotation.evidence_ids,
            text_by_evidence,
        )
    ]
    omitted = len(diagram.annotations) - len(supported)
    if omitted == 0:
        return diagram
    noun = "annotation" if omitted == 1 else "annotations"
    limitation = (
        f"Omitted {omitted} {noun} whose text was not literally visible in cited "
        "evidence."
    )
    return diagram.model_copy(
        update={
            "annotations": supported,
            "limitations": [*diagram.limitations, limitation],
        }
    )


def reground_visible_text_geometry(
    diagram: AnalyzedDiagram,
    observations: ValidatedObservationSet,
) -> AnalyzedDiagram:
    """Anchor invalid model geometry to unique exact-text observations.

    Reconstruction geometry is interpretive, while observation geometry has already
    been transformed deterministically from an attached image into source-image
    coordinates.  When a labeled object or annotation cites the same evidence as one
    unique exact visible-text observation but its model-proposed box misses that
    evidence, the literal observation is the safer geometric authority.

    Ambiguous repeated text, missing observation boxes, and records without shared
    evidence remain untouched so hard validation can still reject them.
    """

    evidence_by_id = {item.id: item for item in observations.evidence}

    def intersects_cited_evidence(
        bbox: NormalizedBox,
        evidence_ids: list[str],
    ) -> bool:
        return any(
            _boxes_intersect(bbox, evidence_by_id[evidence_id].source_bbox)
            for evidence_id in evidence_ids
            if evidence_id in evidence_by_id
        )

    def exact_text_box(text: str, evidence_ids: list[str]) -> NormalizedBox | None:
        normalized = normalize_visible_text(text)
        shared_evidence = set(evidence_ids)
        matches = [
            observation.source_bbox
            for observation in observations.observations
            if observation.source_bbox is not None
            and observation.visible_text is not None
            and normalize_visible_text(observation.visible_text) == normalized
            and shared_evidence.intersection(observation.evidence_ids)
        ]
        return matches[0] if len(matches) == 1 else None

    objects = []
    regrounded_objects = 0
    for item in diagram.objects:
        replacement = None
        if item.visible_label is not None and not intersects_cited_evidence(
            item.bbox,
            item.evidence_ids,
        ):
            replacement = exact_text_box(item.visible_label, item.evidence_ids)
        if replacement is None:
            objects.append(item)
        else:
            objects.append(item.model_copy(update={"bbox": replacement}))
            regrounded_objects += 1

    annotations = []
    regrounded_annotations = 0
    for item in diagram.annotations:
        replacement = None
        if not intersects_cited_evidence(item.bbox, item.evidence_ids):
            replacement = exact_text_box(item.visible_text, item.evidence_ids)
        if replacement is None:
            annotations.append(item)
        else:
            annotations.append(item.model_copy(update={"bbox": replacement}))
            regrounded_annotations += 1

    if regrounded_objects == 0 and regrounded_annotations == 0:
        return diagram
    limitation = (
        "Re-grounded invalid visible-text geometry to validated observations "
        f"({regrounded_objects} objects, {regrounded_annotations} annotations)."
    )
    return diagram.model_copy(
        update={
            "objects": objects,
            "annotations": annotations,
            "limitations": [*diagram.limitations, limitation],
        }
    )


def downgrade_degraded_visible_labels(
    diagram: AnalyzedDiagram,
    observations: ValidatedObservationSet,
) -> AnalyzedDiagram:
    """Omit exact object text when a degraded source lacks high-confidence OCR."""

    degraded_terms = ("degraded", "poor quality", "low quality", "low legibility")
    if not any(
        term in warning.casefold()
        for warning in observations.warnings
        for term in degraded_terms
    ):
        return diagram
    confidence_by_text: dict[str, set[str]] = {}
    for observation in observations.observations:
        if observation.visible_text is None:
            continue
        confidence_by_text.setdefault(
            normalize_visible_text(observation.visible_text), set()
        ).add(observation.confidence)
    objects = []
    omitted = 0
    for item in diagram.objects:
        if item.visible_label is None:
            objects.append(item)
            continue
        confidences = confidence_by_text.get(normalize_visible_text(item.visible_label), set())
        if "high" in confidences:
            objects.append(item)
            continue
        omitted += 1
        objects.append(
            item.model_copy(
                update={
                    "visible_label": None,
                    "normalized_label": None,
                    "reference_numbers": [],
                }
            )
        )
    if omitted == 0:
        return diagram
    noun = "label" if omitted == 1 else "labels"
    limitation = (
        f"Omitted {omitted} exact object {noun} from degraded source text because no "
        "matching high-confidence visible-text observation was available."
    )
    return diagram.model_copy(
        update={
            "objects": objects,
            "limitations": [*diagram.limitations, limitation],
        }
    )


def downgrade_unsupported_relationship_claims(
    diagram: AnalyzedDiagram,
    observations: ValidatedObservationSet,
) -> AnalyzedDiagram:
    """Make connector type and direction neutral unless literal pixels support them."""

    kinds_by_evidence: dict[str, set[str]] = {}
    for observation in observations.observations:
        for evidence_id in observation.evidence_ids:
            kinds_by_evidence.setdefault(evidence_id, set()).add(observation.kind)
    visible_legend_meanings = {
        normalize_visible_text(legend.meaning) for legend in diagram.legends
    }
    relationships = []
    downgraded_types = 0
    downgraded_directions = 0
    for relationship in diagram.relationships:
        updates: dict[str, object] = {}
        if (
            relationship.relation != "unknown"
            and relationship.visible_label is None
            and normalize_visible_text(relationship.relation) not in visible_legend_meanings
        ):
            updates["relation"] = "unknown"
            downgraded_types += 1
        directional = relationship.direction in {"forward", "reverse", "bidirectional"}
        has_arrowhead = any(
            "arrowhead" in kinds_by_evidence.get(evidence_id, set())
            for evidence_id in relationship.evidence_ids
        )
        if directional and not has_arrowhead:
            updates["direction"] = "unclear"
            if relationship.confidence == "high":
                updates["confidence"] = "medium"
            downgraded_directions += 1
        relationships.append(
            relationship.model_copy(update=updates) if updates else relationship
        )
    if not downgraded_types and not downgraded_directions:
        return diagram
    limitations = list(diagram.limitations)
    if downgraded_types:
        noun = "connector" if downgraded_types == 1 else "connectors"
        limitations.append(
            f"Set the semantic type of {downgraded_types} unlabeled {noun} to unknown "
            "because no visible legend established a meaning."
        )
    if downgraded_directions:
        noun = "connector" if downgraded_directions == 1 else "connectors"
        limitations.append(
            f"Set the direction of {downgraded_directions} {noun} to unclear because "
            "their cited evidence contained no explicit arrowhead observation."
        )
    return diagram.model_copy(
        update={"relationships": relationships, "limitations": limitations}
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
        intersects_evidence = any(
            _boxes_intersect(item.bbox, evidence_by_id[evidence_id].source_bbox)
            for evidence_id in item.evidence_ids
            if evidence_id in evidence_by_id
        )
        intersects_exact_text = (
            item.visible_label is not None
            and _box_intersects_exact_text_observation(
                item.bbox,
                item.visible_label,
                item.evidence_ids,
                observations,
            )
        )
        if not intersects_evidence and not intersects_exact_text:
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
            if not _reference_is_observed(reference, cited_text):
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
        ) and not _box_intersects_exact_text_observation(
            annotation.bbox,
            annotation.visible_text,
            annotation.evidence_ids,
            observations,
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


def normalize_duplicate_relationship_ids(diagram: AnalyzedDiagram) -> AnalyzedDiagram:
    """Renumber duplicate relationship IDs without changing relationship meaning.

    Relationship IDs are local mechanical identifiers and are not referenced by other
    semantic records.  A structured model response can therefore be repaired safely by
    assigning duplicate occurrences the next unused canonical ID.  Object, group, and
    annotation IDs are deliberately left alone because other records can refer to them.
    """

    used: set[str] = set()
    next_number = 1
    relationships = []
    changed = False
    for relationship in diagram.relationships:
        relationship_id = relationship.id
        if relationship_id in used:
            while f"relationship-{next_number:04d}" in used:
                next_number += 1
            relationship_id = f"relationship-{next_number:04d}"
            next_number += 1
            relationship = relationship.model_copy(update={"id": relationship_id})
            changed = True
        used.add(relationship_id)
        relationships.append(relationship)
    if not changed:
        return diagram
    return diagram.model_copy(update={"relationships": relationships})
