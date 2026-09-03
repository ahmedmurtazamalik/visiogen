"""G4 renderer-neutral compilation and hard-validation tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from visiogen.design import DiagramDesign
from visiogen.generation.compiler import (
    CompilationError,
    compile_construction_plan,
    compile_v1_design,
)
from visiogen.generation.construction import VisioConstructionPlan
from visiogen.generation.specification import DiagramSpecification, load_specification

SPEC = Path("tests/fixtures/generation_v2/specifications/expert-component.json")


def plan_data() -> dict[str, object]:
    typography = {
        "family": "Arial",
        "size_pt": 10,
        "bold": False,
        "italic": False,
        "color": "#111111",
        "horizontal_align": "center",
        "vertical_align": "middle",
    }
    style = {
        "fill_color": "#FFFFFF",
        "line_color": "#222222",
        "line_weight_pt": 1,
        "line_pattern": "solid",
    }

    def shape(identifier, object_id, master, rect, *, container=None):
        return {
            "id": identifier,
            "object_id": object_id,
            "master": master,
            "rect": rect,
            "text_box": rect,
            "typography": typography,
            "style": style,
            "z_order": 1,
            "ports": [
                {"name": "left", "side": "left", "offset": 0.5},
                {"name": "right", "side": "right", "offset": 0.5},
            ],
            "container": container,
        }

    return {
        "version": 1,
        "specification_version": 1,
        "page": {
            "width": 10,
            "height": 6,
            "orientation": "landscape",
            "margin": 0.5,
            "grid": 0.25,
        },
        "regions": [
            {
                "id": "main_region",
                "name": "Main",
                "rect": {"x": 0.5, "y": 0.5, "width": 9, "height": 5},
            }
        ],
        "guides": [{"id": "main_axis", "axis": "horizontal", "position": 3}],
        "shapes": [
            shape(
                "shape_housing",
                "housing",
                "__template_housing_container__",
                {"x": 1, "y": 1, "width": 8, "height": 4},
                container={
                    "header_text": "Housing",
                    "header_height": 0.4,
                    "padding": 0.3,
                    "member_ids": ["sensor", "controller"],
                    "clipping": "contain",
                },
            ),
            shape(
                "shape_sensor",
                "sensor",
                "__template_sensor__",
                {"x": 2, "y": 2.2, "width": 1.5, "height": 1.5},
            ),
            shape(
                "shape_controller",
                "controller",
                "__template_controller__",
                {"x": 6, "y": 2.4, "width": 2, "height": 1},
            ),
        ],
        "connectors": [
            {
                "id": "connector_sensor_data",
                "relationship_id": "sensor_data",
                "master": "__template_connector__",
                "connector_type": "orthogonal",
                "source_shape_id": "shape_sensor",
                "source_port": "right",
                "target_shape_id": "shape_controller",
                "target_port": "left",
                "waypoints": [{"x": 3.5, "y": 3}, {"x": 6, "y": 3}],
                "bends": [],
                "jumps": False,
                "arrowheads": "end",
                "line_color": "#222222",
                "line_weight_pt": 1,
                "line_pattern": "solid",
                "label": None,
            }
        ],
        "callouts": [
            {
                "id": "callout_sensor",
                "object_id": "sensor",
                "carrier": "__template_reference_callout__",
                "text": "110",
                "rect": {"x": 1.7, "y": 4, "width": 0.8, "height": 0.3},
                "target_anchor": {"x": 2.5, "y": 3},
                "leader_route": [{"x": 2.1, "y": 4}, {"x": 2.5, "y": 3}],
                "z_order": 3,
            },
            {
                "id": "callout_controller",
                "object_id": "controller",
                "carrier": "__template_reference_callout__",
                "text": "120",
                "rect": {"x": 6.5, "y": 4, "width": 0.8, "height": 0.3},
                "target_anchor": {"x": 7, "y": 3},
                "leader_route": [{"x": 6.9, "y": 4}, {"x": 7, "y": 3}],
                "z_order": 3,
            },
        ],
        "traceability": [
            {
                "requirement_id": "internal_alignment",
                "plan_element_ids": ["shape_sensor", "shape_controller", "main_axis"],
                "rationale": "Peers share an axis.",
            },
            {
                "requirement_id": "clear_callouts",
                "plan_element_ids": ["callout_sensor", "callout_controller"],
                "rationale": "Callouts sit outside labels.",
            },
        ],
        "visual_rationale": "A contained signal path.",
    }


def valid_design_data() -> dict[str, object]:
    return {
        "graph": {
            "title": "Flow",
            "diagram_type": "flowchart",
            "orientation": "left_to_right",
            "nodes": [
                {"id": "start", "type": "terminator", "label": "Start"},
                {"id": "work", "type": "process", "label": "Work"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "start",
                    "target": "work",
                    "relation": "flow",
                    "direction": "forward",
                }
            ],
        },
        "layout": {
            "composition": "compact_flow",
            "page_width": 8,
            "page_height": 5,
            "placements": [
                {"node_id": "start", "x": 2, "y": 2.5, "width": 1.5, "height": 0.75},
                {"node_id": "work", "x": 5, "y": 2.5, "width": 1.5, "height": 0.75},
            ],
        },
        "rationale": "Simple flow.",
    }


def _compile(data: dict[str, object]):
    return compile_construction_plan(
        load_specification(SPEC), VisioConstructionPlan.model_validate(data)
    )


def test_compilation_is_deterministic_resolved_and_immutable() -> None:
    first = _compile(plan_data())
    second = _compile(plan_data())

    assert first == second
    assert first.source_engine == "v2"
    by_object = {shape.object_id: shape for shape in first.shapes}
    assert by_object["housing"].master_name == "Housing"
    assert by_object["sensor"].ports[1].x == 3.5
    assert first.connectors[0].route[0].model_dump() == {"x": 3.5, "y": 2.95}
    assert first.connectors[0].route[-1].model_dump() == {"x": 6.0, "y": 2.9}
    with pytest.raises(ValidationError):
        first.shapes[0].z_order = 99
    with pytest.raises(ValidationError):
        first.shapes[0].rect.x = 99


def test_compiler_rejects_ambiguous_ids_ports_and_region_bounds() -> None:
    data = plan_data()
    data["regions"][0]["rect"]["width"] = 10  # type: ignore[index]
    data["regions"][0]["id"] = "main_axis"  # type: ignore[index]
    data["shapes"][1]["ports"][0]["name"] = "right"  # type: ignore[index]

    with pytest.raises(CompilationError) as error:
        _compile(data)

    assert "region 'main_axis' is outside page bounds" in str(error.value)
    assert "shape 'shape_sensor' port names must be unique" in str(error.value)
    assert "plan element IDs must be unique: main_axis" in str(error.value)


def test_compiler_reports_containment_route_and_label_failures() -> None:
    data = plan_data()
    data["shapes"][1]["rect"] = {"x": 1.1, "y": 1.1, "width": 1.5, "height": 1.5}  # type: ignore[index]
    data["shapes"][1]["text_box"] = {"x": 1.0, "y": 1.0, "width": 2, "height": 2}  # type: ignore[index]
    connector = data["connectors"][0]  # type: ignore[index]
    connector["waypoints"] = [{"x": 4, "y": 2}, {"x": 7, "y": 2}]
    connector["label"] = {
        "text": "data",
        "position": {"x": 11, "y": 3},
        "offset": 0,
        "orientation": "horizontal",
        "background": "opaque",
    }

    with pytest.raises(CompilationError) as error:
        _compile(data)

    assert "text box is outside its shape" in str(error.value)
    assert "violates container" in str(error.value)
    assert "non-orthogonal segment" in str(error.value)
    assert "label is outside page bounds" in str(error.value)


def test_compiler_rejects_connector_intersection_and_discontinuous_callout() -> None:
    data = plan_data()
    data["connectors"][0]["waypoints"] = [  # type: ignore[index]
        {"x": 4.5, "y": 2.95},
        {"x": 4.5, "y": 2.9},
    ]
    data["shapes"].append(deepcopy(data["shapes"][1]))  # type: ignore[union-attr,index]
    obstruction = data["shapes"][-1]  # type: ignore[index]
    obstruction.update(
        {
            "id": "shape_obstruction",
            "object_id": "obstruction",
            "rect": {"x": 4.25, "y": 2.5, "width": 0.5, "height": 1},
            "text_box": {"x": 4.25, "y": 2.5, "width": 0.5, "height": 1},
        }
    )
    data["shapes"][0]["container"]["member_ids"].append("obstruction")  # type: ignore[index]
    data["callouts"][0]["leader_route"][-1] = {"x": 3, "y": 3}  # type: ignore[index]
    specification_data = load_specification(SPEC).model_dump(mode="json")
    specification_data["objects"].append(
        {
            "id": "obstruction",
            "label": "Obstruction",
            "type": "component",
            "parent_id": "housing",
        }
    )
    specification = DiagramSpecification.model_validate(specification_data)

    with pytest.raises(CompilationError) as error:
        compile_construction_plan(
            specification, VisioConstructionPlan.model_validate(data)
        )

    assert "intersects unrelated shape 'shape_obstruction'" in str(error.value)
    assert "leader does not end at its target anchor" in str(error.value)


def test_schema_rejects_formula_and_package_instruction_fields() -> None:
    data = plan_data()
    data["shapes"][0]["formula"] = "GUARD(PinX)"  # type: ignore[index]
    data["package_instruction"] = "replace page1.xml"

    with pytest.raises(ValidationError) as error:
        VisioConstructionPlan.model_validate(data)

    assert "formula" in str(error.value)
    assert "package_instruction" in str(error.value)


def test_v1_adapter_is_explicitly_tagged_and_deterministic() -> None:
    design = DiagramDesign.model_validate(valid_design_data())

    first = compile_v1_design(design)

    assert first == compile_v1_design(design)
    assert first.source_engine == "v1_compatibility"
    assert first.shapes and first.connectors
