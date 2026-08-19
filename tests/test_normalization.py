from pathlib import Path

import pytest

from visiogen.models import DiagramEdge, DiagramGraph, DiagramNode
from visiogen.normalization import (
    GraphNormalizationError,
    normalize_extracted_graph,
    normalize_graph,
)


def graph(*, nodes=None, edges=None) -> DiagramGraph:
    return DiagramGraph(
        title="Test graph",
        diagram_type="system_block",
        orientation="left_to_right",
        nodes=nodes or [],
        edges=edges or [],
    )


def node(node_id: str, node_type: str = "component", **kwargs) -> DiagramNode:
    return DiagramNode(id=node_id, type=node_type, label=node_id, **kwargs)


def edge(source: str = "a", target: str = "b", edge_id: str | None = None) -> DiagramEdge:
    return DiagramEdge(id=edge_id, source=source, target=target)


def test_duplicate_node_ids_are_rejected():
    with pytest.raises(GraphNormalizationError, match="duplicate node ID 'a'"):
        normalize_graph(graph(nodes=[node("a"), node("a")]))


def test_duplicate_non_empty_edge_ids_are_rejected():
    with pytest.raises(GraphNormalizationError, match="duplicate edge ID 'e1'"):
        normalize_graph(
            graph(nodes=[node("a"), node("b")], edges=[edge(edge_id="e1"), edge(edge_id="e1")])
        )


def test_missing_edge_ids_are_assigned_deterministically_without_collisions():
    source = graph(
        nodes=[node("a"), node("b")],
        edges=[edge(edge_id="e1"), edge(), edge()],
    )

    normalized = normalize_graph(source)

    assert [item.id for item in normalized.edges] == ["e1", "e2", "e3"]
    assert [item.id for item in source.edges] == ["e1", None, None]


@pytest.mark.parametrize(
    ("bad_edge", "message"),
    [
        (edge(source="missing"), "source 'missing'"),
        (edge(target="missing"), "target 'missing'"),
    ],
)
def test_dangling_edge_endpoints_are_rejected(bad_edge, message):
    with pytest.raises(GraphNormalizationError, match=message):
        normalize_graph(graph(nodes=[node("a"), node("b")], edges=[bad_edge]))


def test_missing_parent_is_rejected():
    with pytest.raises(GraphNormalizationError, match="parent 'missing'"):
        normalize_graph(graph(nodes=[node("child", parent_id="missing")]))


def test_parent_must_be_container_capable():
    with pytest.raises(GraphNormalizationError, match="not container-capable"):
        normalize_graph(nodes_graph := graph(nodes=[node("parent"), node("child", parent_id="parent")]))
    assert nodes_graph.nodes[1].parent_id == "parent"


def test_self_parent_is_rejected():
    with pytest.raises(GraphNormalizationError, match="cannot contain itself"):
        normalize_graph(graph(nodes=[node("a", "housing", parent_id="a")]))


def test_containment_cycle_is_rejected():
    with pytest.raises(GraphNormalizationError, match="containment cycle"):
        normalize_graph(
            graph(
                nodes=[
                    node("a", "housing", parent_id="b"),
                    node("b", "subsystem", parent_id="a"),
                ]
            )
        )


def test_more_than_one_containment_level_is_rejected():
    with pytest.raises(GraphNormalizationError, match="one level"):
        normalize_graph(
            graph(
                nodes=[
                    node("outer", "housing"),
                    node("inner", "subsystem", parent_id="outer"),
                    node("child", parent_id="inner"),
                ]
            )
        )


def test_duplicate_trimmed_reference_numbers_are_rejected():
    with pytest.raises(GraphNormalizationError, match="duplicate reference number '100'"):
        normalize_graph(
            graph(
                nodes=[
                    node("a", reference_number="100"),
                    node("b", reference_number=" 100 "),
                ]
            )
        )


def test_normalization_preserves_order_and_semantics():
    source = graph(
        nodes=[node("b", notes="keep"), node("a")],
        edges=[DiagramEdge(source="b", target="a", relation="data", label="payload")],
    )

    normalized = normalize_graph(source)

    assert [item.id for item in normalized.nodes] == ["b", "a"]
    assert normalized.nodes[0].notes == "keep"
    assert normalized.edges[0].relation == "data"
    assert normalized.edges[0].label == "payload"


def test_extraction_boundary_rejects_geometry():
    source = graph(nodes=[node("a", x=1.0)])

    with pytest.raises(GraphNormalizationError, match="geometry"):
        normalize_extracted_graph(source)


def test_extraction_collapses_equivalent_reciprocal_edges_to_bidirectional():
    source = graph(
        nodes=[node("processor"), node("memory")],
        edges=[
            DiagramEdge(source="processor", target="memory", relation="data"),
            DiagramEdge(source="memory", target="processor", relation="data"),
        ],
    )

    normalized = normalize_extracted_graph(source)

    assert len(normalized.edges) == 1
    assert normalized.edges[0].source == "processor"
    assert normalized.edges[0].target == "memory"
    assert normalized.edges[0].direction == "bidirectional"
    assert len(source.edges) == 2


@pytest.mark.parametrize(
    "fixture_name",
    ["linear_flow.json", "basic_system.json", "nested_subsystem.json"],
)
def test_reviewed_graph_fixtures_normalize_and_round_trip(fixture_name):
    fixture_path = Path(__file__).parent / "fixtures" / "graphs" / fixture_name
    loaded = DiagramGraph.model_validate_json(fixture_path.read_text())

    normalized = normalize_extracted_graph(loaded)
    restored = DiagramGraph.model_validate_json(normalized.model_dump_json())

    assert restored == normalized
    assert restored.has_geometry is False
