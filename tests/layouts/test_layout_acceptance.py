from itertools import combinations
from pathlib import Path
from typing import Protocol

import pytest

from visiogen.layout import LayoutResult
from visiogen.layouts.fallback_layered import FallbackLayeredLayout
from visiogen.layouts.graphviz_layout import GraphvizLayout
from visiogen.models import DiagramGraph, DiagramNode

EXPECTED = Path(__file__).parents[1] / "fixtures" / "graphs" / "expected"
LAYOUT_FIXTURES = Path(__file__).parents[1] / "fixtures" / "layout"
GRAPH_NAMES = [
    "basic_system",
    "bidirectional_architecture",
    "eco_headphone",
    "isolated_process",
    "linear_flow",
    "login_decision",
    "method_loop",
    "nested_subsystem",
    "patent_schematic",
]


class LayoutStrategy(Protocol):
    def layout(self, graph: DiagramGraph) -> LayoutResult: ...


def load_expected(name: str) -> DiagramGraph:
    return DiagramGraph.model_validate_json((EXPECTED / f"{name}.json").read_text())


def box(node: DiagramNode) -> tuple[float, float, float, float]:
    assert node.x is not None and node.y is not None
    assert node.width is not None and node.height is not None
    return (
        node.x - node.width / 2,
        node.y - node.height / 2,
        node.x + node.width / 2,
        node.y + node.height / 2,
    )


def assert_common_geometry(result: LayoutResult) -> None:
    assert result.page.width > 0
    assert result.page.height > 0
    nodes = {node.id: node for node in result.graph.nodes}
    container_ids = {
        node.parent_id for node in result.graph.nodes if node.parent_id is not None
    }

    for node in result.graph.nodes:
        left, bottom, right, top = box(node)
        assert node.width is not None and node.width > 0
        assert node.height is not None and node.height > 0
        assert left >= -1e-6, node.id
        assert bottom >= -1e-6, node.id
        assert right <= result.page.width + 1e-6, node.id
        assert top <= result.page.height + 1e-6, node.id

    ordinary_nodes = [
        node for node in result.graph.nodes if node.id not in container_ids
    ]
    for left_node, right_node in combinations(ordinary_nodes, 2):
        left_box = box(left_node)
        right_box = box(right_node)
        separated = (
            left_box[2] <= right_box[0]
            or right_box[2] <= left_box[0]
            or left_box[3] <= right_box[1]
            or right_box[3] <= left_box[1]
        )
        assert separated, f"{left_node.id} overlaps {right_node.id}"

    for child in result.graph.nodes:
        if child.parent_id is None:
            continue
        container_box = box(nodes[child.parent_id])
        child_box = box(child)
        assert container_box[0] < child_box[0]
        assert container_box[1] < child_box[1]
        assert container_box[2] > child_box[2]
        assert container_box[3] > child_box[3]


@pytest.mark.parametrize("strategy_type", [GraphvizLayout, FallbackLayeredLayout])
@pytest.mark.parametrize("graph_name", GRAPH_NAMES)
def test_reviewed_graphs_satisfy_shared_geometry_contract(
    strategy_type: type[LayoutStrategy], graph_name: str
) -> None:
    graph = load_expected(graph_name)
    original_json = graph.model_dump_json()
    strategy = strategy_type()

    first = strategy.layout(graph)
    second = strategy.layout(graph)

    assert_common_geometry(first)
    assert first.model_dump_json() == second.model_dump_json()
    assert graph.model_dump_json() == original_json


@pytest.mark.parametrize("strategy_type", [GraphvizLayout, FallbackLayeredLayout])
def test_medium_25_node_system_satisfies_shared_geometry_contract(
    strategy_type: type[LayoutStrategy],
) -> None:
    graph = DiagramGraph.model_validate_json(
        (LAYOUT_FIXTURES / "medium_system_25.json").read_text()
    )
    original_json = graph.model_dump_json()
    strategy = strategy_type()

    first = strategy.layout(graph)
    second = strategy.layout(graph)

    assert len(first.graph.nodes) == 25
    assert_common_geometry(first)
    assert first.model_dump_json() == second.model_dump_json()
    assert graph.model_dump_json() == original_json
