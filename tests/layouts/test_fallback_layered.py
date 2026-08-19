from itertools import combinations
from pathlib import Path

import pytest

from visiogen.layout import LayoutError
from visiogen.layouts.fallback_layered import FallbackLayeredLayout
from visiogen.models import DiagramGraph, DiagramNode

FIXTURES = Path(__file__).parents[1] / "fixtures" / "graphs" / "expected"


def load_graph(name: str) -> DiagramGraph:
    return DiagramGraph.model_validate_json((FIXTURES / f"{name}.json").read_text())


def boxes_overlap(left: DiagramNode, right: DiagramNode) -> bool:
    assert left.x is not None and left.y is not None
    assert left.width is not None and left.height is not None
    assert right.x is not None and right.y is not None
    assert right.width is not None and right.height is not None
    return not (
        left.x + left.width / 2 <= right.x - right.width / 2
        or right.x + right.width / 2 <= left.x - left.width / 2
        or left.y + left.height / 2 <= right.y - right.height / 2
        or right.y + right.height / 2 <= left.y - left.height / 2
    )


def test_fallback_layout_is_deterministic_and_respects_top_to_bottom_flow() -> None:
    graph = load_graph("linear_flow")

    first = FallbackLayeredLayout().layout(graph)
    second = FallbackLayeredLayout().layout(graph)

    assert first.model_dump_json() == second.model_dump_json()
    positioned = {node.id: node for node in first.graph.nodes}
    start_y = positioned["start"].y
    review_y = positioned["review"].y
    finish_y = positioned["finish"].y
    assert start_y is not None and review_y is not None and finish_y is not None
    assert start_y > review_y > finish_y
    assert graph.has_geometry is False


def test_fallback_layout_respects_left_to_right_system_orientation() -> None:
    result = FallbackLayeredLayout().layout(load_graph("basic_system"))
    positioned = {node.id: node for node in result.graph.nodes}
    sensor_x = positioned["sensor"].x
    processor_x = positioned["processor"].x
    memory_x = positioned["memory"].x
    assert sensor_x is not None and processor_x is not None and memory_x is not None
    assert sensor_x < processor_x
    assert sensor_x < memory_x


def test_fallback_layout_handles_cycles_without_overlapping_nodes() -> None:
    result = FallbackLayeredLayout().layout(load_graph("method_loop"))
    nodes = {node.id: node for node in result.graph.nodes}

    for left, right in combinations(result.graph.nodes, 2):
        assert not boxes_overlap(left, right), f"{left.id} overlaps {right.id}"

    start_y = nodes["start"].y
    initialize_y = nodes["initialize"].y
    remaining_y = nodes["remaining"].y
    complete_y = nodes["complete"].y
    assert all(
        value is not None
        for value in (start_y, initialize_y, remaining_y, complete_y)
    )
    assert start_y is not None and initialize_y is not None
    assert remaining_y is not None and complete_y is not None
    assert start_y > initialize_y > remaining_y > complete_y


def test_fallback_layout_sizes_container_around_children() -> None:
    result = FallbackLayeredLayout().layout(load_graph("nested_subsystem"))
    nodes = {node.id: node for node in result.graph.nodes}
    container = nodes["control"]
    assert container.x is not None and container.y is not None
    assert container.width is not None and container.height is not None

    left = container.x - container.width / 2
    right = container.x + container.width / 2
    bottom = container.y - container.height / 2
    top = container.y + container.height / 2
    for child_id in ("processor", "memory"):
        child = nodes[child_id]
        assert child.x is not None and child.y is not None
        assert child.width is not None and child.height is not None
        assert child.x - child.width / 2 > left
        assert child.x + child.width / 2 < right
        assert child.y - child.height / 2 > bottom
        assert child.y + child.height / 2 < top


def test_fallback_layout_rejects_empty_graph_clearly() -> None:
    graph = DiagramGraph(
        title="Empty",
        diagram_type="flowchart",
        orientation="top_to_bottom",
    )

    with pytest.raises(LayoutError, match="at least one node"):
        FallbackLayeredLayout().layout(graph)
