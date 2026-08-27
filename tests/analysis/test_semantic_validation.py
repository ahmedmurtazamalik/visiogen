"""Hard validation for A3 evidence transforms and semantic references."""

import pytest

from visiogen.analysis.models import PreparedCandidate, PreparedDerivative
from visiogen.analysis.semantics import (
    AnalyzedDiagram,
    AnalyzedGroup,
    DiagramAnnotation,
    LegendMapping,
    NormalizedPoint,
    RawObservationBatch,
)
from visiogen.analysis.validation import (
    AnalysisValidationError,
    discard_unsupported_annotations,
    discard_unsupported_legends,
    downgrade_unsupported_relationship_endpoints,
    sanitize_object_grounding,
    validate_analyzed_diagram,
    validate_observations,
)
from visiogen.documents.models import NormalizedBox


def _prepared() -> PreparedCandidate:
    full = NormalizedBox(left=0, top=0, right=1, bottom=1)
    tile_region = NormalizedBox(left=0.5, top=0.25, right=1, bottom=0.75)
    return PreparedCandidate(
        candidate_id="candidate-0001",
        derivatives=[
            PreparedDerivative(
                id="candidate-0001-crop",
                kind="crop",
                artifact_path="assets/crop.png",
                sha256="1" * 64,
                byte_size=10,
                width_px=100,
                height_px=100,
                source_region=full,
            ),
            PreparedDerivative(
                id="candidate-0001-overview",
                kind="overview",
                artifact_path="assets/overview.png",
                sha256="2" * 64,
                byte_size=10,
                width_px=100,
                height_px=100,
                source_region=full,
            ),
            PreparedDerivative(
                id="candidate-0001-tile-001",
                kind="tile",
                artifact_path="assets/tile.png",
                sha256="3" * 64,
                byte_size=10,
                width_px=100,
                height_px=100,
                source_region=tile_region,
            ),
        ],
    )


def _raw_observations() -> RawObservationBatch:
    return RawObservationBatch.model_validate(
        {
            "candidate_id": "candidate-0001",
            "evidence": [
                {
                    "id": "evidence-0001",
                    "derivative_id": "candidate-0001-tile-001",
                    "local_bbox": {"left": 0.2, "top": 0.2, "right": 0.4, "bottom": 0.4},
                },
                {
                    "id": "evidence-0002",
                    "derivative_id": "candidate-0001-overview",
                    "local_bbox": {"left": 0.6, "top": 0.2, "right": 0.8, "bottom": 0.4},
                },
                {
                    "id": "evidence-0003",
                    "derivative_id": "candidate-0001-overview",
                    "local_bbox": {"left": 0.3, "top": 0.25, "right": 0.7, "bottom": 0.35},
                },
            ],
            "observations": [
                {
                    "id": "observation-0001",
                    "kind": "visible_text",
                    "geometry_derivative_id": "candidate-0001-tile-001",
                    "local_bbox": {"left": 0.2, "top": 0.2, "right": 0.4, "bottom": 0.4},
                    "local_path": [],
                    "visible_text": "Sensor 10",
                    "properties": [],
                    "evidence_ids": ["evidence-0001"],
                    "confidence": "high",
                    "alternatives": [],
                },
                {
                    "id": "observation-0002",
                    "kind": "visible_text",
                    "geometry_derivative_id": "candidate-0001-overview",
                    "local_bbox": {"left": 0.6, "top": 0.2, "right": 0.8, "bottom": 0.4},
                    "local_path": [],
                    "visible_text": "Processor 20",
                    "properties": [],
                    "evidence_ids": ["evidence-0002"],
                    "confidence": "high",
                    "alternatives": [],
                },
                {
                    "id": "observation-0003",
                    "kind": "connector",
                    "geometry_derivative_id": "candidate-0001-overview",
                    "local_bbox": None,
                    "local_path": [{"x": 0.3, "y": 0.3}, {"x": 0.7, "y": 0.3}],
                    "visible_text": None,
                    "properties": [{"name": "line_style", "value": "solid"}],
                    "evidence_ids": ["evidence-0003"],
                    "confidence": "high",
                    "alternatives": [],
                },
            ],
            "warnings": [],
        }
    )


def _diagram(*, first_label: str = "Sensor 10") -> AnalyzedDiagram:
    return AnalyzedDiagram.model_validate(
        {
            "candidate_id": "candidate-0001",
            "title": None,
            "family": "system_block",
            "orientation": "left_to_right",
            "objects": [
                {
                    "id": "object-0001",
                    "visible_label": first_label,
                    "normalized_label": first_label.casefold(),
                    "semantic_type": "sensor",
                    "visual_shape": "rectangle",
                    "reference_numbers": ["10"],
                    "parent_id": None,
                    "bbox": {"left": 0.6, "top": 0.35, "right": 0.7, "bottom": 0.45},
                    "evidence_ids": ["evidence-0001"],
                    "confidence": "high",
                    "alternatives": [],
                },
                {
                    "id": "object-0002",
                    "visible_label": "Processor 20",
                    "normalized_label": "processor 20",
                    "semantic_type": "processor",
                    "visual_shape": "rectangle",
                    "reference_numbers": ["20"],
                    "parent_id": None,
                    "bbox": {"left": 0.6, "top": 0.2, "right": 0.8, "bottom": 0.4},
                    "evidence_ids": ["evidence-0002"],
                    "confidence": "high",
                    "alternatives": [],
                },
            ],
            "relationships": [
                {
                    "id": "relationship-0001",
                    "source_id": "object-0001",
                    "target_id": "object-0002",
                    "source_certainty": "known",
                    "target_certainty": "known",
                    "direction": "forward",
                    "relation": "data",
                    "visible_label": None,
                    "normalized_label": None,
                    "path": [{"x": 0.65, "y": 0.4}, {"x": 0.75, "y": 0.3}],
                    "line_style": "solid",
                    "evidence_ids": ["evidence-0003"],
                    "confidence": "high",
                    "alternatives": [],
                }
            ],
            "groups": [],
            "legends": [],
            "limitations": [],
            "confidence": "high",
        }
    )


def test_observation_validation_transforms_tile_local_coordinates() -> None:
    validated = validate_observations(_raw_observations(), _prepared())

    evidence = validated.evidence[0]
    assert evidence.source_bbox.left == pytest.approx(0.6)
    assert evidence.source_bbox.top == pytest.approx(0.35)
    assert evidence.source_bbox.right == pytest.approx(0.7)
    assert evidence.source_bbox.bottom == pytest.approx(0.45)
    assert validated.observations[0].source_bbox == evidence.source_bbox
    assert validated.observations[2].source_path[1].x == pytest.approx(0.7)


def test_observation_validation_rejects_unknown_derivative_and_evidence() -> None:
    raw = _raw_observations()
    raw.evidence[0].derivative_id = "missing"
    raw.observations[0].evidence_ids = ["evidence-9999"]

    with pytest.raises(AnalysisValidationError) as captured:
        validate_observations(raw, _prepared())

    assert "unknown derivative" in str(captured.value)
    assert "unknown evidence" in str(captured.value)


@pytest.mark.parametrize(
    "bbox",
    [
        {"left": 0.3, "top": 0.3, "right": 0.3, "bottom": 0.7},
        {"left": 0.7, "top": 0.3, "right": 0.3, "bottom": 0.7},
        {"left": 0.3, "top": 0.7, "right": 0.7, "bottom": 0.3},
    ],
)
def test_invalid_observation_bbox_uses_its_visible_path(
    bbox: dict[str, float],
) -> None:
    payload = _raw_observations().model_dump(mode="json")
    connector = payload["observations"][2]
    connector["local_bbox"] = bbox

    batch = RawObservationBatch.model_validate(payload)

    assert batch.observations[2].local_bbox is None
    assert len(batch.observations[2].local_path) == 2


def test_invalid_observation_bbox_without_path_remains_rejected() -> None:
    payload = _raw_observations().model_dump(mode="json")
    connector = payload["observations"][2]
    connector["local_bbox"] = {
        "left": 0.7,
        "top": 0.3,
        "right": 0.3,
        "bottom": 0.7,
    }
    connector["local_path"] = []

    with pytest.raises(ValueError, match="positive width and height"):
        RawObservationBatch.model_validate(payload)


def test_semantic_validation_accepts_grounded_objects_and_relationships() -> None:
    observations = validate_observations(_raw_observations(), _prepared())

    assert validate_analyzed_diagram(_diagram(), observations) == _diagram()


def test_semantic_validation_rejects_invented_visible_label() -> None:
    observations = validate_observations(_raw_observations(), _prepared())

    with pytest.raises(AnalysisValidationError, match="not present in cited evidence"):
        validate_analyzed_diagram(_diagram(first_label="Camera 10"), observations)


def test_semantic_validation_accepts_multiline_label_split_across_observations() -> None:
    raw = _raw_observations()
    raw.observations[0].visible_text = "Sensor"
    raw.observations.insert(
        1,
        raw.observations[0].model_copy(
            update={"id": "observation-0004", "visible_text": "10"}
        ),
    )
    observations = validate_observations(raw, _prepared())

    diagram = _diagram(first_label="Sensor\n10")
    diagram.objects[0] = diagram.objects[0].model_copy(
        update={"normalized_label": "sensor 10"}
    )

    assert validate_analyzed_diagram(diagram, observations).objects[0].visible_label == (
        "Sensor\n10"
    )


def test_object_label_citation_is_regrounded_to_exact_observation_evidence() -> None:
    observations = validate_observations(_raw_observations(), _prepared())
    diagram = _diagram()
    diagram.objects[0] = diagram.objects[0].model_copy(
        update={"evidence_ids": ["evidence-0002"]}
    )

    sanitized = sanitize_object_grounding(diagram, observations)

    assert sanitized.objects[0].evidence_ids == ["evidence-0002", "evidence-0001"]
    assert sanitized.limitations == [
        "Re-grounded 1 object label to exact visible-text evidence."
    ]
    assert validate_analyzed_diagram(sanitized, observations) == sanitized


def test_final_object_sanitization_omits_only_unsupported_text() -> None:
    observations = validate_observations(_raw_observations(), _prepared())
    diagram = _diagram(first_label="Invented 99")
    diagram.objects[0] = diagram.objects[0].model_copy(
        update={"reference_numbers": ["99"]}
    )

    first_attempt = sanitize_object_grounding(diagram, observations)
    assert first_attempt == diagram
    with pytest.raises(AnalysisValidationError, match="not present in cited evidence"):
        validate_analyzed_diagram(first_attempt, observations)

    final_attempt = sanitize_object_grounding(
        diagram,
        observations,
        omit_unsupported=True,
    )
    assert final_attempt.objects[0].visible_label is None
    assert final_attempt.objects[0].normalized_label is None
    assert final_attempt.objects[0].reference_numbers == []
    assert final_attempt.limitations == [
        "Omitted 1 object label not literally visible in observation evidence.",
        "Omitted 1 object reference number not visibly evidenced.",
    ]
    assert validate_analyzed_diagram(final_attempt, observations) == final_attempt


def test_numeric_reference_accepts_attached_unicode_subscript_run() -> None:
    raw = _raw_observations()
    raw.observations[0].visible_text = "SP₆"
    observations = validate_observations(raw, _prepared())
    diagram = _diagram(first_label="SP₆")
    diagram.objects[0] = diagram.objects[0].model_copy(
        update={"normalized_label": "sp₆", "reference_numbers": ["₆"]}
    )

    assert validate_analyzed_diagram(diagram, observations) == diagram

    invalid = diagram.model_copy(deep=True)
    invalid.objects[0] = invalid.objects[0].model_copy(
        update={"reference_numbers": ["₆", "P"]}
    )
    with pytest.raises(AnalysisValidationError, match="reference number 'P'"):
        validate_analyzed_diagram(invalid, observations)


def test_observation_validation_rejects_duplicate_ids_and_cross_derivative_evidence() -> None:
    raw = _raw_observations()
    raw.evidence.append(raw.evidence[0])
    raw.observations[1].evidence_ids = ["evidence-0001"]

    with pytest.raises(AnalysisValidationError) as captured:
        validate_observations(raw, _prepared())

    assert "evidence IDs must be unique" in str(captured.value)
    assert "no evidence on its geometry derivative" in str(captured.value)


def test_semantic_validation_rejects_unsupported_references_and_containment() -> None:
    observations = validate_observations(_raw_observations(), _prepared())
    diagram = _diagram()
    first, second = diagram.objects
    diagram.objects = [
        first.model_copy(
            update={"parent_id": second.id, "reference_numbers": ["99"]}
        ),
        second.model_copy(update={"parent_id": first.id}),
    ]
    diagram.relationships[0] = diagram.relationships[0].model_copy(
        update={"source_id": "object-9999"}
    )

    with pytest.raises(AnalysisValidationError) as captured:
        validate_analyzed_diagram(diagram, observations)

    message = str(captured.value)
    assert "reference number '99' is not visibly evidenced" in message
    assert "containment cycle" in message
    assert "not geometrically contained" in message
    assert "unknown source object 'object-9999'" in message


def test_semantic_validation_requires_connector_geometry_evidence() -> None:
    observations = validate_observations(_raw_observations(), _prepared())
    diagram = _diagram()
    diagram.relationships[0] = diagram.relationships[0].model_copy(
        update={
            "evidence_ids": ["evidence-0001"],
            "path": [
                NormalizedPoint(x=0.95, y=0.95),
                NormalizedPoint(x=0.99, y=0.99),
            ],
        }
    )

    with pytest.raises(AnalysisValidationError) as captured:
        validate_analyzed_diagram(diagram, observations)

    assert "cites no connector or arrowhead observation" in str(captured.value)
    assert "path is not near its cited evidence" in str(captured.value)


def test_unsupported_relationship_endpoints_are_downgraded_to_ambiguous() -> None:
    observations = validate_observations(_raw_observations(), _prepared())
    diagram = _diagram()
    relationship = diagram.relationships[0]
    diagram.relationships[0] = relationship.model_copy(
        update={
            "path": [
                NormalizedPoint(x=0.3, y=0.3),
                NormalizedPoint(x=0.4, y=0.3),
            ]
        }
    )

    sanitized = downgrade_unsupported_relationship_endpoints(diagram)

    assert sanitized.relationships[0].source_certainty == "ambiguous"
    assert sanitized.relationships[0].target_certainty == "ambiguous"
    assert sanitized.limitations == [
        "Downgraded 2 relationship endpoints to ambiguous because the reconstructed "
        "path did not geometrically reach the claimed object."
    ]
    assert validate_analyzed_diagram(sanitized, observations) == sanitized


def test_semantic_validation_grounding_covers_groups_legends_and_titles() -> None:
    observations = validate_observations(_raw_observations(), _prepared())
    diagram = _diagram().model_copy(
        update={
            "title": "Invented title",
            "title_evidence_ids": ["evidence-0001"],
            "groups": [
                AnalyzedGroup(
                    id="group-0001",
                    kind="zone",
                    visible_label=None,
                    object_ids=["object-0001"],
                    bbox=NormalizedBox(left=0.85, top=0.8, right=0.95, bottom=0.9),
                    evidence_ids=["evidence-0001"],
                    confidence="high",
                )
            ],
            "legends": [
                LegendMapping(
                    symbol="solid",
                    meaning="Invented meaning",
                    evidence_ids=["evidence-0001"],
                    confidence="high",
                )
            ],
        }
    )

    with pytest.raises(AnalysisValidationError) as captured:
        validate_analyzed_diagram(diagram, observations)

    message = str(captured.value)
    assert "title is not present" in message
    assert "Group 'group-0001' does not intersect its cited evidence" in message
    assert "does not intersect member object" in message
    assert "Legend meaning is not present" in message


def test_unsupported_legend_meanings_are_discarded_without_weakening_validation() -> None:
    observations = validate_observations(_raw_observations(), _prepared())
    diagram = _diagram().model_copy(
        update={
            "legends": [
                LegendMapping(
                    symbol="solid",
                    meaning="Invented meaning",
                    evidence_ids=["evidence-0001"],
                    confidence="high",
                )
            ],
            "limitations": ["Original limitation"],
        }
    )

    sanitized = discard_unsupported_legends(diagram, observations)

    assert sanitized.legends == []
    assert sanitized.limitations == [
        "Original limitation",
        "Omitted 1 legend mapping whose meaning was not literally visible in cited evidence.",
    ]
    assert validate_analyzed_diagram(sanitized, observations) == sanitized


def test_semantic_validation_preserves_grounded_notes_and_callouts() -> None:
    observations = validate_observations(_raw_observations(), _prepared())
    valid = _diagram().model_copy(
        update={
            "annotations": [
                DiagramAnnotation(
                    id="annotation-0001",
                    kind="callout",
                    visible_text="Sensor 10",
                    attached_object_ids=["object-0001"],
                    bbox=NormalizedBox(left=0.6, top=0.35, right=0.7, bottom=0.45),
                    evidence_ids=["evidence-0001"],
                    confidence="high",
                )
            ]
        }
    )

    assert validate_analyzed_diagram(valid, observations) == valid

    invalid = valid.model_copy(deep=True)
    invalid.annotations[0] = invalid.annotations[0].model_copy(
        update={
            "visible_text": "Invented callout",
            "attached_object_ids": ["object-9999"],
            "bbox": NormalizedBox(left=0.8, top=0.8, right=0.9, bottom=0.9),
        }
    )
    with pytest.raises(AnalysisValidationError) as captured:
        validate_analyzed_diagram(invalid, observations)

    message = str(captured.value)
    assert "unknown object 'object-9999'" in message
    assert "does not intersect its cited evidence" in message
    assert "text is not present in cited evidence" in message


def test_unsupported_annotations_are_discarded_without_weakening_validation() -> None:
    observations = validate_observations(_raw_observations(), _prepared())
    grounded = DiagramAnnotation(
        id="annotation-0001",
        kind="callout",
        visible_text="Sensor 10",
        attached_object_ids=["object-0001"],
        bbox=NormalizedBox(left=0.6, top=0.35, right=0.7, bottom=0.45),
        evidence_ids=["evidence-0001"],
        confidence="high",
    )
    invented = grounded.model_copy(
        update={"id": "annotation-0002", "visible_text": "Invented callout"}
    )
    diagram = _diagram().model_copy(
        update={
            "annotations": [grounded, invented],
            "limitations": ["Original limitation"],
        }
    )

    sanitized = discard_unsupported_annotations(diagram, observations)

    assert sanitized.annotations == [grounded]
    assert sanitized.limitations == [
        "Original limitation",
        "Omitted 1 annotation whose text was not literally visible in cited evidence.",
    ]
    assert validate_analyzed_diagram(sanitized, observations) == sanitized

    with pytest.raises(AnalysisValidationError, match="text is not present"):
        validate_analyzed_diagram(diagram, observations)
