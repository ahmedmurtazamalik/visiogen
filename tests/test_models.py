import pytest
from pydantic import ValidationError

from vega.models import DiagramEdge, DiagramGraph, DiagramNode


def sample_graph() -> DiagramGraph:
    return DiagramGraph(
        title="Login flow",
        diagram_type="flowchart",
        orientation="top_to_bottom",
        nodes=[
            DiagramNode(id="start", type="terminator", label="Start"),
            DiagramNode(id="login", type="process", label="Log in"),
        ],
        edges=[DiagramEdge(id="e1", source="start", target="login")],
    )


def test_graph_round_trip_preserves_semantics():
    graph = sample_graph()

    restored = DiagramGraph.model_validate_json(graph.model_dump_json())

    assert restored == graph
    assert restored.edges[0].relation == "flow"
    assert restored.edges[0].direction == "forward"
    assert restored.edges[0].style == "solid"


def test_unsupported_node_type_is_rejected():
    with pytest.raises(ValidationError):
        DiagramNode(id="n1", type="unicorn", label="Invalid")


def test_pre_layout_graph_has_no_geometry():
    assert sample_graph().has_geometry is False


def test_post_layout_graph_reports_geometry():
    graph = sample_graph().model_copy(deep=True)
    graph.nodes[0].x = 1.0
    graph.nodes[0].y = 2.0
    graph.nodes[0].width = 1.5
    graph.nodes[0].height = 0.75

    assert graph.has_geometry is True
