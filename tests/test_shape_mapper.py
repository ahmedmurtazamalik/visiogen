from itertools import product
from typing import get_args

import pytest

from visiogen.models import DirectionType, NodeType, RelationType
from visiogen.shape_mapper import (
    NODE_VISUALS,
    PRODUCTION_TEMPLATE_MARKERS,
    ShapeMappingError,
    map_edge_visual,
    map_node_visual,
)


def test_every_node_type_has_an_explicit_template_mapping() -> None:
    node_types = set(get_args(NodeType))

    assert set(NODE_VISUALS) == node_types
    for node_type in node_types:
        visual = map_node_visual(node_type)
        assert visual.marker in PRODUCTION_TEMPLATE_MARKERS
        assert visual.default_width > 0
        assert visual.default_height > 0


def test_semantic_aliases_reuse_the_intended_visual_templates() -> None:
    expected_aliases = {
        "data_store": "database",
        "memory": "database",
        "processor": "controller",
        "actuator": "component",
        "communication_module": "component",
        "transducer": "sensor",
        "service": "external_system",
    }

    for alias, canonical in expected_aliases.items():
        assert map_node_visual(alias).marker == map_node_visual(canonical).marker

    assert map_node_visual("subsystem").container_capable is True
    assert map_node_visual("housing").container_capable is True


@pytest.mark.parametrize(
    ("direction", "begin_arrow", "end_arrow"),
    [
        ("forward", False, True),
        ("reverse", True, False),
        ("bidirectional", True, True),
        ("none", False, False),
    ],
)
def test_direction_deterministically_controls_connector_arrows(
    direction: DirectionType,
    begin_arrow: bool,
    end_arrow: bool,
) -> None:
    for relation in get_args(RelationType):
        first = map_edge_visual(relation, direction)
        second = map_edge_visual(relation, direction)

        assert first == second
        assert first.begin_arrow is begin_arrow
        assert first.end_arrow is end_arrow


def test_relation_defaults_control_style_and_weight() -> None:
    assert map_edge_visual("flow", "forward").line_style == "solid"
    assert map_edge_visual("association", "none").line_style == "dotted"
    assert map_edge_visual("mechanical", "none").line_style == "dashed"
    assert map_edge_visual("power", "forward").line_weight == pytest.approx(2.0)
    assert map_edge_visual("data", "forward").line_weight == pytest.approx(1.0)


def test_explicit_line_style_wins_over_relation_default() -> None:
    assert map_edge_visual("association", "none", line_style="solid").line_style == "solid"
    assert map_edge_visual("flow", "forward", line_style="dashed").line_style == "dashed"
    assert map_edge_visual("power", "forward", line_style="dotted").line_style == "dotted"


def test_every_relation_direction_combination_resolves() -> None:
    combinations = product(get_args(RelationType), get_args(DirectionType))

    for relation, direction in combinations:
        visual = map_edge_visual(relation, direction)
        assert visual.marker == "__template_connector__"


def test_missing_template_inventory_marker_raises_clear_error() -> None:
    available = PRODUCTION_TEMPLATE_MARKERS - {"__template_process__"}

    with pytest.raises(
        ShapeMappingError,
        match="Template inventory is missing marker '__template_process__'",
    ):
        map_node_visual("process", available_markers=available)

    without_connector = PRODUCTION_TEMPLATE_MARKERS - {"__template_connector__"}
    with pytest.raises(
        ShapeMappingError,
        match="Template inventory is missing marker '__template_connector__'",
    ):
        map_edge_visual("flow", "forward", available_markers=without_connector)


def test_unknown_semantic_values_raise_clear_errors() -> None:
    with pytest.raises(ShapeMappingError, match="Unknown node type 'unknown'"):
        map_node_visual("unknown")  # type: ignore[arg-type]

    with pytest.raises(ShapeMappingError, match="Unknown relation type 'unknown'"):
        map_edge_visual("unknown", "forward")  # type: ignore[arg-type]

    with pytest.raises(ShapeMappingError, match="Unknown direction 'sideways'"):
        map_edge_visual("flow", "sideways")  # type: ignore[arg-type]

    with pytest.raises(ShapeMappingError, match="Unknown line style 'wavy'"):
        map_edge_visual("flow", "forward", line_style="wavy")  # type: ignore[arg-type]


def test_mapping_data_is_immutable() -> None:
    with pytest.raises(TypeError):
        NODE_VISUALS["process"] = NODE_VISUALS["decision"]  # type: ignore[index]
