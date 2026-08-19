from pathlib import Path
import subprocess

import pytest

from visiogen.layout import LayoutError, size_node
from visiogen.layouts.graphviz_layout import GraphvizLayout, build_dot
from visiogen.models import DiagramEdge, DiagramGraph, DiagramNode

FIXTURES = Path(__file__).parents[1] / "fixtures" / "graphs" / "expected"
DOT_FIXTURES = Path(__file__).parents[1] / "fixtures" / "dot"


def load_graph(name: str) -> DiagramGraph:
    return DiagramGraph.model_validate_json((FIXTURES / f"{name}.json").read_text())


def test_build_dot_is_deterministic_and_respects_requested_orientation() -> None:
    graph = load_graph("linear_flow")

    first = build_dot(graph)
    second = build_dot(graph)

    assert first == second
    assert 'rankdir="TB"' in first
    assert 'nodesep="0.7500"' in first
    assert 'ranksep="1.0000"' in first
    assert first.index('"finish" [') < first.index('"start" [')
    assert first.index('"review" -> "finish"') < first.index('"start" -> "review"')


@pytest.mark.parametrize("graph_name", ["linear_flow", "basic_system", "nested_subsystem"])
def test_build_dot_matches_reviewed_snapshot(graph_name: str) -> None:
    assert build_dot(load_graph(graph_name)) == (
        DOT_FIXTURES / f"{graph_name}.dot"
    ).read_text()


def test_build_dot_escapes_quoted_ids_and_labels_for_real_graphviz() -> None:
    graph = DiagramGraph(
        title="Quoted identifiers",
        diagram_type="system_block",
        orientation="left_to_right",
        nodes=[
            DiagramNode(
                id='source "A"',
                type="service",
                label='Say "go"\\then',
            ),
            DiagramNode(id="target\\B", type="database", label="Store result"),
        ],
        edges=[
            DiagramEdge(
                id="edge",
                source='source "A"',
                target="target\\B",
                relation="data",
                direction="forward",
                style="solid",
            )
        ],
    )

    dot = build_dot(graph)
    result = GraphvizLayout().layout(graph)

    assert '"source \\"A\\""' in dot
    assert '"target\\\\B"' in dot
    assert 'label="Say \\"go\\"\\\\then"' in dot
    assert {node.id for node in result.graph.nodes} == {'source "A"', "target\\B"}


def test_build_dot_represents_one_level_containment_as_cluster() -> None:
    dot = build_dot(load_graph("nested_subsystem"))

    cluster_start = dot.index('subgraph "cluster_control"')
    cluster_end = dot.index("  }", cluster_start)
    cluster = dot[cluster_start:cluster_end]
    assert '"processor" [' in cluster
    assert '"memory" [' in cluster
    assert '  "control" [' not in dot


def test_build_dot_weights_directional_relations_but_not_associations() -> None:
    graph = load_graph("basic_system")
    graph.edges.append(
        DiagramEdge(
            id="association",
            source="sensor",
            target="memory",
            relation="association",
            direction="none",
            style="dotted",
        )
    )

    dot = build_dot(graph)

    assert '"sensor" -> "processor" [weight="3"]' in dot
    assert (
        '"sensor" -> "memory" [weight="1", constraint="false"]'
        in dot
    )


def test_graphviz_layout_invokes_dot_and_parses_plain_coordinates() -> None:
    captured: dict[str, object] = {}
    plain = """graph 1 4 6
node start 2 5 2.6 0.9 Start solid box black lightgrey
node review 2 3 2.625 0.75 Review solid box black lightgrey
node finish 2 1 2.6 0.9 Finish solid box black lightgrey
stop
"""

    def runner(
        command: list[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        captured.update(
            command=command,
            input=input,
            text=text,
            capture_output=capture_output,
            check=check,
            timeout=timeout,
        )
        return subprocess.CompletedProcess(command, 0, stdout=plain, stderr="")

    graph = load_graph("linear_flow")
    result = GraphvizLayout(runner=runner).layout(graph)

    assert captured["command"] == ["dot", "-Tplain"]
    assert 'rankdir="TB"' in str(captured["input"])
    positioned = {node.id: node for node in result.graph.nodes}
    assert (positioned["start"].x, positioned["start"].y) == (2.5, 5.5)
    assert (result.page.width, result.page.height) == (5.0, 7.0)
    assert graph.has_geometry is False


def test_graphviz_layout_reports_missing_executable_as_layout_error() -> None:
    def missing_runner(
        command: list[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    with pytest.raises(LayoutError, match="Graphviz executable.*dot"):
        GraphvizLayout(runner=missing_runner).layout(load_graph("linear_flow"))


def test_graphviz_layout_translates_dot_process_failure() -> None:
    def failing_runner(
        command: list[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, command, stderr="syntax error")

    with pytest.raises(LayoutError, match="Graphviz layout command failed"):
        GraphvizLayout(runner=failing_runner).layout(load_graph("linear_flow"))


@pytest.mark.parametrize(
    "plain",
    [
        "",
        "graph 1 invalid 6\nstop\n",
        "graph 1 4 6\nstop\n",
    ],
)
def test_graphviz_layout_rejects_malformed_plain_output(plain: str) -> None:
    def malformed_runner(
        command: list[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=plain, stderr="")

    with pytest.raises(LayoutError, match="malformed Graphviz plain output"):
        GraphvizLayout(runner=malformed_runner).layout(load_graph("linear_flow"))


def test_real_graphviz_layout_is_deterministic_and_preserves_flow_direction() -> None:
    graph = load_graph("linear_flow")

    first = GraphvizLayout().layout(graph)
    second = GraphvizLayout().layout(graph)

    assert first.model_dump_json() == second.model_dump_json()
    positioned = {node.id: node for node in first.graph.nodes}
    start_y = positioned["start"].y
    review_y = positioned["review"].y
    finish_y = positioned["finish"].y
    assert start_y is not None and review_y is not None and finish_y is not None
    assert start_y > review_y > finish_y
    assert graph.has_geometry is False


def test_real_graphviz_layout_preserves_canonical_node_dimensions() -> None:
    graph = load_graph("basic_system")

    result = GraphvizLayout().layout(graph)

    original = {node.id: node for node in graph.nodes}
    for positioned in result.graph.nodes:
        expected = size_node(original[positioned.id])
        assert (positioned.width, positioned.height) == (
            expected.width,
            expected.height,
        )


def test_graphviz_layout_applies_wrapped_label_only_to_output_graph() -> None:
    original_label = (
        "Validate the submitted customer request against every authorization "
        "constraint before final approval"
    )
    graph = DiagramGraph(
        title="Long label",
        diagram_type="flowchart",
        orientation="top_to_bottom",
        nodes=[DiagramNode(id="review", type="process", label=original_label)],
    )

    result = GraphvizLayout().layout(graph)

    assert "\n" in result.graph.nodes[0].label
    assert result.graph.nodes[0].label == size_node(graph.nodes[0]).wrapped_label
    assert graph.nodes[0].label == original_label


def test_real_graphviz_layout_sizes_container_around_children() -> None:
    result = GraphvizLayout().layout(load_graph("nested_subsystem"))
    nodes = {node.id: node for node in result.graph.nodes}
    container = nodes["control"]
    assert all(
        value is not None
        for value in (container.x, container.y, container.width, container.height)
    )

    assert container.x is not None
    assert container.y is not None
    assert container.width is not None
    assert container.height is not None
    container_left = container.x - container.width / 2
    container_right = container.x + container.width / 2
    container_bottom = container.y - container.height / 2
    container_top = container.y + container.height / 2
    for child_id in ("processor", "memory"):
        child = nodes[child_id]
        assert child.x is not None and child.y is not None
        assert child.width is not None and child.height is not None
        assert child.x - child.width / 2 > container_left
        assert child.x + child.width / 2 < container_right
        assert child.y - child.height / 2 > container_bottom
        assert child.y + child.height / 2 < container_top
