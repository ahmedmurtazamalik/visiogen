"""G1 professional DiagramSpecification contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from visiogen.generation.specification import (
    DiagramSpecification,
    SpecificationError,
    load_specification,
)
from visiogen.generation.specification_workflow import (
    SpecificationWorkflowError,
    StructuredSpecificationWorkflow,
)
from visiogen.providers.base import ProviderResponse

FIXTURE_ROOT = Path("tests/fixtures/generation_v2/specifications")


def specification_data() -> dict[str, object]:
    return {
        "version": 1,
        "title": "Sensor processing system",
        "purpose": "Show how sensed data is processed and stored.",
        "audience": "System reviewers",
        "diagram_type": "system_block",
        "notation": "system",
        "orientation": "left_to_right",
        "primary_flow": "sensor to processor to memory",
        "objects": [
            {
                "id": "sensor",
                "label": "Sensor",
                "type": "sensor",
                "required": True,
                "parent_id": None,
                "reference_number": "110",
                "importance": "secondary",
                "notes": None,
            },
            {
                "id": "processor",
                "label": "Processor",
                "type": "processor",
                "required": True,
                "parent_id": None,
                "reference_number": "120",
                "importance": "primary",
                "notes": None,
            },
            {
                "id": "memory",
                "label": "Memory",
                "type": "memory",
                "required": False,
                "parent_id": None,
                "reference_number": None,
                "importance": "supporting",
                "notes": "Capacity is unknown.",
            },
        ],
        "relationships": [
            {
                "id": "sensor_data",
                "source": "sensor",
                "target": "processor",
                "relation": "data",
                "direction": "forward",
                "label": None,
                "required": True,
            }
        ],
        "constraints": [
            {
                "id": "primary_order",
                "kind": "ordering",
                "object_ids": ["sensor", "processor", "memory"],
                "strength": "hard",
                "axis": None,
                "minimum_distance": None,
            },
            {
                "id": "processor_clearance",
                "kind": "separation",
                "object_ids": ["processor", "memory"],
                "strength": "preference",
                "axis": None,
                "minimum_distance": 0.25,
            },
        ],
        "drafting": {
            "shape_family": "native Visio system shapes",
            "color_direction": "neutral blue",
            "typography": "sans serif",
            "connector_style": "orthogonal",
        },
        "review_items": [
            {
                "id": "memory_capacity",
                "kind": "unknown",
                "description": "Memory capacity is not specified.",
                "permitted": True,
            }
        ],
        "visual_requirements": [
            {
                "id": "no_overlap",
                "description": "No shape or label overlaps.",
                "metric": "overlap_count",
                "operator": "eq",
                "value": 0,
            }
        ],
        "forbidden_conditions": ["Do not imply an unmentioned control path."],
    }


def test_expert_specification_round_trips_json_and_yaml() -> None:
    json_spec = load_specification(FIXTURE_ROOT / "expert-flow.json")
    yaml_spec = load_specification(FIXTURE_ROOT / "expert-system.yaml")

    assert json_spec.title == "Review flow"
    assert yaml_spec.title == "Sensor processing system"
    assert DiagramSpecification.model_validate_json(json_spec.model_dump_json()) == json_spec
    assert DiagramSpecification.model_validate_json(yaml_spec.model_dump_json()) == yaml_spec


def test_specification_rejects_unknown_references_and_extra_fields() -> None:
    unknown = specification_data()
    unknown["relationships"][0]["target"] = "missing"  # type: ignore[index]
    with pytest.raises(ValidationError, match="references unknown objects: missing"):
        DiagramSpecification.model_validate(unknown)

    extra = specification_data()
    extra["objects"][0]["x"] = 1.0  # type: ignore[index]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DiagramSpecification.model_validate(extra)


def test_specification_rejects_containment_and_hard_ordering_cycles() -> None:
    containment = specification_data()
    containment["objects"][0]["parent_id"] = "processor"  # type: ignore[index]
    containment["objects"][1]["parent_id"] = "sensor"  # type: ignore[index]
    with pytest.raises(ValidationError, match="containment cycle"):
        DiagramSpecification.model_validate(containment)

    ordering = specification_data()
    ordering["constraints"].append(  # type: ignore[union-attr]
        {
            "id": "reverse_order",
            "kind": "ordering",
            "object_ids": ["memory", "sensor"],
            "strength": "hard",
            "axis": None,
            "minimum_distance": None,
        }
    )
    with pytest.raises(ValidationError, match="contradictory hard ordering"):
        DiagramSpecification.model_validate(ordering)


def test_loader_rejects_unknown_extensions(tmp_path: Path) -> None:
    path = tmp_path / "spec.txt"
    path.write_text("{}")
    with pytest.raises(SpecificationError, match=".json, .yaml, or .yml"):
        load_specification(path)


class FakeCall:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        self.calls.append((system_prompt, user_prompt))
        return ProviderResponse(
            content=next(self.responses),
            request_id=f"request-{len(self.calls)}",
            elapsed_ms=10.0,
            transport_prompt=f"transport-{len(self.calls)}",
        )


def test_text_adapter_returns_validated_specification_and_provenance() -> None:
    response = json.dumps(specification_data())
    call = FakeCall([response])

    result = StructuredSpecificationWorkflow(call).specify("A sensor feeds a processor")

    assert result.specification.objects[0].id == "sensor"
    assert result.raw_responses == (response,)
    assert result.request_ids == ("request-1",)
    assert result.elapsed_ms == 10.0
    assert "coordinates" in call.calls[0][0]


def test_text_adapter_repairs_once_then_fails_clearly() -> None:
    repaired = json.dumps(specification_data())
    call = FakeCall(["{}", repaired])
    assert StructuredSpecificationWorkflow(call).specify("A system").attempts == 2
    assert "Validation findings" in call.calls[1][1]

    invalid = FakeCall(["{}", "{}"])
    with pytest.raises(SpecificationWorkflowError, match="after one repair"):
        StructuredSpecificationWorkflow(invalid).specify("A system")
