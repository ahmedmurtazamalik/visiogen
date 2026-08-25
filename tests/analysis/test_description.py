"""Deterministic A4 description contracts and artifact publication."""

import json
from pathlib import Path

import pytest

from visiogen.analysis.description import (
    DescriptionValidationError,
    DiagramDescription,
    compose_diagram_description,
    render_description_markdown,
    validate_diagram_description,
    write_description_bundle,
)
from visiogen.analysis.semantics import AnalyzedDiagram

_GOLDEN = Path(__file__).parents[1] / "fixtures/analysis/descriptions/accessibility_system.md"


def _diagram() -> AnalyzedDiagram:
    return AnalyzedDiagram.model_validate(
        {
            "candidate_id": "candidate-0042",
            "title": "Control *[A]*",
            "title_evidence_ids": ["evidence-0001"],
            "family": "system_block",
            "orientation": "left_to_right",
            "objects": [
                {
                    "id": "object-0001",
                    "visible_label": "Platform",
                    "normalized_label": "platform",
                    "semantic_type": "subsystem",
                    "visual_shape": "container rectangle",
                    "reference_numbers": [],
                    "parent_id": None,
                    "bbox": {"left": 0.05, "top": 0.1, "right": 0.95, "bottom": 0.9},
                    "evidence_ids": ["evidence-0002"],
                    "confidence": "high",
                    "alternatives": [],
                },
                {
                    "id": "object-0002",
                    "visible_label": "Sensor 10",
                    "normalized_label": "sensor 10",
                    "semantic_type": "sensor",
                    "visual_shape": "rounded rectangle",
                    "reference_numbers": ["10"],
                    "parent_id": "object-0001",
                    "bbox": {"left": 0.15, "top": 0.35, "right": 0.4, "bottom": 0.6},
                    "evidence_ids": ["evidence-0003"],
                    "confidence": "high",
                    "alternatives": [],
                },
                {
                    "id": "object-0003",
                    "visible_label": None,
                    "normalized_label": None,
                    "semantic_type": "external node",
                    "visual_shape": "circle",
                    "reference_numbers": [],
                    "parent_id": None,
                    "bbox": {"left": 0.75, "top": 0.35, "right": 0.9, "bottom": 0.6},
                    "evidence_ids": ["evidence-0004"],
                    "confidence": "low",
                    "alternatives": [
                        {
                            "value": "off-page reference",
                            "reason": "the symbol has no readable label",
                            "confidence": "low",
                        }
                    ],
                },
            ],
            "relationships": [
                {
                    "id": "relationship-0001",
                    "source_id": "object-0002",
                    "target_id": "object-0003",
                    "source_certainty": "known",
                    "target_certainty": "ambiguous",
                    "direction": "unclear",
                    "relation": "communication",
                    "visible_label": "bus_[1]",
                    "normalized_label": "bus_[1]",
                    "path": [{"x": 0.4, "y": 0.48}, {"x": 0.75, "y": 0.48}],
                    "line_style": "faint dashed line",
                    "evidence_ids": ["evidence-0005"],
                    "confidence": "medium",
                    "alternatives": [
                        {
                            "value": "forward communication",
                            "reason": "a partial mark may be an arrowhead",
                            "confidence": "medium",
                        },
                        {
                            "value": "undirected association",
                            "reason": "the mark may be image damage",
                            "confidence": "medium",
                        },
                    ],
                }
            ],
            "groups": [
                {
                    "id": "group-0001",
                    "kind": "functional zone",
                    "visible_label": "Lane A",
                    "object_ids": ["object-0001", "object-0002"],
                    "bbox": {"left": 0.05, "top": 0.1, "right": 0.65, "bottom": 0.9},
                    "evidence_ids": ["evidence-0006"],
                    "confidence": "high",
                }
            ],
            "legends": [
                {
                    "symbol": "⇢",
                    "meaning": "uncertain flow",
                    "evidence_ids": ["evidence-0007"],
                    "confidence": "medium",
                }
            ],
            "limitations": [
                "The right-hand endpoint is blurred and its direction is not established."
            ],
            "confidence": "medium",
        }
    )


def test_description_matches_reviewed_accessible_markdown() -> None:
    description = compose_diagram_description(_diagram())

    assert render_description_markdown(description) == _GOLDEN.read_text()
    assert [section.name for section in description.sections] == [
        "identity",
        "layout",
        "groups",
        "objects",
        "relationships",
        "annotations",
        "ambiguities",
        "limitations",
    ]


def test_description_json_round_trips_without_input_mutation() -> None:
    diagram = _diagram()
    before = diagram.model_dump_json()

    first = compose_diagram_description(diagram)
    second = compose_diagram_description(diagram)
    restored = DiagramDescription.model_validate_json(first.model_dump_json())

    assert first == second == restored
    assert diagram.model_dump_json() == before


def test_description_validation_rejects_unknown_and_omitted_references() -> None:
    diagram = _diagram()
    description = compose_diagram_description(diagram)
    relationship = description.sections[4].statements[0]
    relationship.object_ids.append("object-9999")

    with pytest.raises(DescriptionValidationError, match="unknown object 'object-9999'"):
        validate_diagram_description(description, diagram)

    clean = compose_diagram_description(diagram)
    for section in clean.sections:
        for statement in section.statements:
            statement.relationship_ids = []
    with pytest.raises(DescriptionValidationError, match="omits relationship"):
        validate_diagram_description(clean, diagram)


def test_description_bundle_is_atomic_and_byte_stable(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = write_description_bundle(_diagram(), first_dir)
    second = write_description_bundle(_diagram(), second_dir)

    assert first == second
    assert {item.name for item in first_dir.iterdir()} == {
        "description.json",
        "description.md",
        "manifest.json",
    }
    for name in ("description.json", "description.md", "manifest.json"):
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()
    assert json.loads((first_dir / "description.json").read_text())["candidate_id"] == (
        "candidate-0042"
    )


def test_markdown_escapes_source_controlled_markup() -> None:
    markdown = render_description_markdown(compose_diagram_description(_diagram()))

    assert "Control \\*\\[A\\]\\*" in markdown
    assert "bus\\_\\[1\\]" in markdown
