import json
import math

import pytest

from visiogen.design import (
    DesignValidationError,
    DiagramDesign,
    validate_design,
)


def valid_design_data() -> dict:
    return {
        "graph": {
            "title": "Sensor system",
            "diagram_type": "system_block",
            "orientation": "left_to_right",
            "nodes": [
                {"id": "sensor", "type": "sensor", "label": "Sensor"},
                {"id": "processor", "type": "processor", "label": "Processor"},
            ],
            "edges": [
                {
                    "id": "data_flow",
                    "source": "sensor",
                    "target": "processor",
                    "relation": "data",
                    "direction": "forward",
                    "label": None,
                    "style": "solid",
                }
            ],
        },
        "layout": {
            "composition": "balanced_hierarchy",
            "page_width": 8.0,
            "page_height": 5.0,
            "placements": [
                {"node_id": "sensor", "x": 2.0, "y": 2.5, "width": 1.5, "height": 1.0},
                {"node_id": "processor", "x": 6.0, "y": 2.5, "width": 1.8, "height": 1.0},
            ],
            "connector_hints": [
                {"edge_id": "data_flow", "source_side": "right", "target_side": "left"}
            ],
        },
        "rationale": "Keep the data flow visually direct.",
    }


def test_valid_design_preserves_ai_geometry_and_normalizes_graph() -> None:
    design = DiagramDesign.model_validate(valid_design_data())

    validated = validate_design(design)
    layout = validated.to_layout_result()

    assert layout.page.width == 8.0
    assert layout.graph.nodes[0].x == 2.0
    assert layout.graph.nodes[1].x == 6.0
    assert layout.graph.edges[0].id == "data_flow"
    assert validated.layout.composition == "balanced_hierarchy"


def test_design_schema_rejects_non_positive_geometry() -> None:
    data = valid_design_data()
    data["layout"]["placements"][0]["width"] = 0

    with pytest.raises(ValueError):
        DiagramDesign.model_validate(data)


def test_design_schema_rejects_non_finite_geometry() -> None:
    data = valid_design_data()
    data["layout"]["placements"][0]["x"] = math.nan

    with pytest.raises(ValueError):
        DiagramDesign.model_validate(data)


def test_design_validation_rejects_duplicate_connector_hints() -> None:
    data = valid_design_data()
    data["layout"]["connector_hints"].append(
        dict(data["layout"]["connector_hints"][0])
    )

    with pytest.raises(DesignValidationError, match="Duplicate connector hint"):
        validate_design(DiagramDesign.model_validate(data))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["layout"]["placements"].pop(), "missing placement"),
        (
            lambda data: data["layout"]["placements"].append(
                {"node_id": "ghost", "x": 4.0, "y": 4.0, "width": 1.0, "height": 1.0}
            ),
            "unknown node",
        ),
        (
            lambda data: data["layout"]["placements"].__setitem__(
                1,
                {"node_id": "processor", "x": 2.2, "y": 2.5, "width": 1.8, "height": 1.0},
            ),
            "overlap",
        ),
        (
            lambda data: data["layout"]["connector_hints"].__setitem__(
                0, {"edge_id": "ghost", "source_side": "right", "target_side": "left"}
            ),
            "unknown edge",
        ),
    ],
)
def test_design_validation_reports_hard_failures(mutate, message: str) -> None:
    data = valid_design_data()
    mutate(data)
    design = DiagramDesign.model_validate_json(json.dumps(data))

    with pytest.raises(DesignValidationError, match=message):
        validate_design(design)


def test_child_must_fit_inside_container() -> None:
    data = valid_design_data()
    data["graph"]["nodes"] = [
        {"id": "housing", "type": "housing", "label": "Housing"},
        {"id": "sensor", "type": "sensor", "label": "Sensor", "parent_id": "housing"},
    ]
    data["graph"]["edges"] = []
    data["layout"]["placements"] = [
        {"node_id": "housing", "x": 4.0, "y": 2.5, "width": 4.0, "height": 3.0},
        {"node_id": "sensor", "x": 6.5, "y": 2.5, "width": 1.0, "height": 1.0},
    ]
    data["layout"]["connector_hints"] = []

    with pytest.raises(DesignValidationError, match="outside container"):
        validate_design(DiagramDesign.model_validate(data))
