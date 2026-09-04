"""G3 construction-plan schema, validation, and planner tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from visiogen.generation.construction import (
    ConstructionPlanError,
    VisioConstructionPlan,
    validate_construction_plan,
)
from visiogen.generation.planner import (
    ConstructionPlanningError,
    StructuredConstructionPlanner,
    build_construction_prompt,
)
from visiogen.generation.specification import load_specification
from visiogen.providers.base import ProviderResponse

SPEC = Path("tests/fixtures/generation_v2/specifications/expert-component.json")


def plan_data() -> dict[str, object]:
    text = {"family": "Arial", "size_pt": 10, "bold": False, "italic": False,
            "color": "#111111", "horizontal_align": "center", "vertical_align": "middle"}
    style = {"fill_color": "#FFFFFF", "line_color": "#222222",
             "line_weight_pt": 1, "line_pattern": "solid"}
    def shape(identifier, object_id, master, rect, *, container=None):
        return {"id": identifier, "object_id": object_id, "master": master,
                "rect": rect, "text_box": rect, "typography": text, "style": style,
                "z_order": 1, "ports": [{"name": "left", "side": "left", "offset": 0.5},
                                          {"name": "right", "side": "right", "offset": 0.5}],
                "container": container}
    return {
        "version": 1, "specification_version": 1,
        "page": {"width": 10, "height": 6, "orientation": "landscape", "margin": 0.5, "grid": 0.25},
        "regions": [{"id": "main_region", "name": "Main", "rect": {"x": 0.5, "y": 0.5, "width": 9, "height": 5}}],
        "guides": [{"id": "main_axis", "axis": "horizontal", "position": 3}],
        "shapes": [
            shape("shape_housing", "housing", "__template_housing_container__", {"x": 1, "y": 1, "width": 8, "height": 4}, container={"header_text": "Housing", "header_height": 0.4, "padding": 0.3, "member_ids": ["sensor", "controller"], "clipping": "contain"}),
            shape("shape_sensor", "sensor", "__template_sensor__", {"x": 2, "y": 2.2, "width": 1.5, "height": 1.5}),
            shape("shape_controller", "controller", "__template_controller__", {"x": 6, "y": 2.4, "width": 2, "height": 1}),
        ],
        "connectors": [{"id": "connector_sensor_data", "relationship_id": "sensor_data", "master": "__template_connector__", "connector_type": "orthogonal", "source_shape_id": "shape_sensor", "source_port": "right", "target_shape_id": "shape_controller", "target_port": "left", "waypoints": [{"x": 3.5, "y": 3}, {"x": 6, "y": 3}], "bends": [], "jumps": False, "arrowheads": "end", "line_color": "#222222", "line_weight_pt": 1, "line_pattern": "solid", "label": None}],
        "callouts": [
            {"id": "callout_sensor", "object_id": "sensor", "carrier": "__template_reference_callout__", "text": "110", "rect": {"x": 1.7, "y": 4, "width": 0.8, "height": 0.3}, "target_anchor": {"x": 2.5, "y": 3}, "leader_route": [{"x": 2.1, "y": 4}, {"x": 2.5, "y": 3}], "z_order": 3},
            {"id": "callout_controller", "object_id": "controller", "carrier": "__template_reference_callout__", "text": "120", "rect": {"x": 6.5, "y": 4, "width": 0.8, "height": 0.3}, "target_anchor": {"x": 7, "y": 3}, "leader_route": [{"x": 6.9, "y": 4}, {"x": 7, "y": 3}], "z_order": 3}
        ],
        "traceability": [
            {"requirement_id": "internal_alignment", "plan_element_ids": ["shape_sensor", "shape_controller", "main_axis"], "rationale": "Peers share an axis."},
            {"requirement_id": "clear_callouts", "plan_element_ids": ["callout_sensor", "callout_controller"], "rationale": "Callouts sit outside labels."}
        ],
        "visual_rationale": "A contained left-to-right signal path with external callouts."
    }


def test_complete_plan_round_trips_and_validates() -> None:
    specification = load_specification(SPEC)
    plan = VisioConstructionPlan.model_validate(plan_data())
    assert validate_construction_plan(specification, plan) == plan
    assert VisioConstructionPlan.model_validate_json(plan.model_dump_json()) == plan


def test_validation_rejects_semantic_and_traceability_drift() -> None:
    specification = load_specification(SPEC)
    plan = VisioConstructionPlan.model_validate(plan_data())
    plan.connectors[0].arrowheads = "begin"
    plan.shapes[0].container.member_ids.remove("sensor")
    plan.traceability.pop()
    with pytest.raises(ConstructionPlanError) as error:
        validate_construction_plan(specification, plan)
    message = str(error.value)
    assert "arrowheads contradict direction" in message
    assert "omits member 'sensor'" in message
    assert "missing constraint traceability: clear_callouts" in message


def test_validation_rejects_callout_for_object_without_reference_number() -> None:
    specification = load_specification(SPEC)
    data = plan_data()
    data["callouts"].append(  # type: ignore[union-attr]
        {
            "id": "callout_housing",
            "object_id": "housing",
            "carrier": "__template_reference_callout__",
            "text": "Housing note",
            "rect": {"x": 1, "y": 5.2, "width": 1, "height": 0.3},
            "target_anchor": {"x": 1, "y": 3},
            "leader_route": [{"x": 1.5, "y": 5.2}, {"x": 1, "y": 3}],
            "z_order": 3,
        }
    )
    plan = VisioConstructionPlan.model_validate(data)

    with pytest.raises(ConstructionPlanError, match="must be omitted.*no reference number"):
        validate_construction_plan(specification, plan)


class FakeCall:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def __call__(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return ProviderResponse(content=next(self.responses), request_id=f"r{len(self.calls)}", elapsed_ms=5, transport_prompt="transport")


def test_planner_uses_versioned_approved_examples_and_preserves_provenance() -> None:
    response = json.dumps(plan_data())
    call = FakeCall([response])
    result = StructuredConstructionPlanner(call).plan(load_specification(SPEC))
    assert result.attempts == 1
    assert result.request_ids == ("r1",)
    assert result.prompt_version == 1 and result.examples_version == 1
    assert "expert-flow.json" in call.calls[0][0]
    assert "expert-system.yaml" in call.calls[0][0]
    assert "expert-component.json" in call.calls[0][0]
    assert "Housing" in call.calls[0][1]


def test_planner_repairs_once_and_then_fails() -> None:
    valid = json.dumps(plan_data())
    call = FakeCall(["{}", valid])
    assert StructuredConstructionPlanner(call).plan(load_specification(SPEC)).attempts == 2
    assert "Findings" in call.calls[1][1]
    with pytest.raises(ConstructionPlanningError, match="after one repair") as failure:
        StructuredConstructionPlanner(FakeCall(["{}", "{}"])).plan(load_specification(SPEC))
    assert [item.content for item in failure.value.responses] == ["{}", "{}"]
    assert len(failure.value.user_prompts) == 2
    assert "Field required" in failure.value.validation_error


def test_planner_repairs_compiler_findings_before_returning() -> None:
    invalid = plan_data()
    invalid["connectors"][0]["waypoints"][0] = {"x": 3.5, "y": 2.95}  # type: ignore[index]
    valid = plan_data()
    call = FakeCall([json.dumps(invalid), json.dumps(valid)])

    result = StructuredConstructionPlanner(call).plan(load_specification(SPEC))

    assert result.attempts == 2
    assert "zero-length segment" in call.calls[1][1]


def test_prompt_forbids_package_authoring() -> None:
    prompt = build_construction_prompt()
    assert "VSDX XML" in prompt and "ShapeSheet formulas" in prompt
