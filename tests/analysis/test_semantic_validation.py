"""Hard validation for A3 evidence transforms and semantic references."""

import pytest

from visiogen.analysis.models import PreparedCandidate, PreparedDerivative
from visiogen.analysis.semantics import AnalyzedDiagram, RawObservationBatch
from visiogen.analysis.validation import (
    AnalysisValidationError,
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


def test_semantic_validation_accepts_grounded_objects_and_relationships() -> None:
    observations = validate_observations(_raw_observations(), _prepared())

    assert validate_analyzed_diagram(_diagram(), observations) == _diagram()


def test_semantic_validation_rejects_invented_visible_label() -> None:
    observations = validate_observations(_raw_observations(), _prepared())

    with pytest.raises(AnalysisValidationError, match="not present in cited evidence"):
        validate_analyzed_diagram(_diagram(first_label="Camera 10"), observations)
