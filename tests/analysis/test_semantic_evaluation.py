"""Deterministic scoring tests for A3 reviewed ground truth."""

from visiogen.analysis.evaluation import aggregate_semantic_scores, score_semantic_case
from visiogen.analysis.semantics import AnalyzedDiagram


def _diagram() -> AnalyzedDiagram:
    return AnalyzedDiagram.model_validate(
        {
            "candidate_id": "candidate-0001",
            "title": None,
            "title_evidence_ids": [],
            "family": "system_block",
            "orientation": "left_to_right",
            "objects": [
                {
                    "id": "object-0001",
                    "visible_label": "Source",
                    "normalized_label": "source",
                    "semantic_type": "component",
                    "visual_shape": "rectangle",
                    "reference_numbers": ["10"],
                    "parent_id": None,
                    "bbox": {"left": 0.1, "top": 0.2, "right": 0.3, "bottom": 0.4},
                    "evidence_ids": ["evidence-0001"],
                    "confidence": "high",
                    "alternatives": [],
                },
                {
                    "id": "object-0002",
                    "visible_label": "Target",
                    "normalized_label": "target",
                    "semantic_type": "component",
                    "visual_shape": "rectangle",
                    "reference_numbers": [],
                    "parent_id": None,
                    "bbox": {"left": 0.7, "top": 0.2, "right": 0.9, "bottom": 0.4},
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
                    "relation": "flow",
                    "visible_label": None,
                    "normalized_label": None,
                    "path": [],
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


def test_semantic_scoring_counts_exact_objects_references_edges_and_family() -> None:
    case = {
        "id": "case",
        "expected_family": "system_block",
        "allowed_additional_object_labels": [],
        "objects": [
            {"label": "Source", "references": ["10"]},
            {"label": "Target", "references": []},
        ],
        "relationships": [
            {"source": "Source", "target": "Target", "direction": "forward"}
        ],
        "ambiguous_direction": False,
    }

    score = score_semantic_case(case, _diagram())
    aggregate = aggregate_semantic_scores([score])

    assert aggregate.object_precision == 1
    assert aggregate.object_recall == 1
    assert aggregate.reference_recall == 1
    assert aggregate.edge_precision == 1
    assert aggregate.edge_recall == 1
    assert aggregate.direction_accuracy == 1
    assert aggregate.family_accuracy == 1
