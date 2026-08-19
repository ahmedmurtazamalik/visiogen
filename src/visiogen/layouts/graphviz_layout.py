"""Deterministic Graphviz DOT layout strategy."""

from __future__ import annotations

import shlex
import subprocess
from typing import Protocol

from visiogen.layout import (
    LayoutError,
    LayoutResult,
    add_container_geometry,
    apply_geometry,
    fit_page_to_geometry,
    size_node,
    wrapped_graph,
)
from visiogen.models import DiagramGraph, DiagramNode, RelationType

_NODE_SPACING = 0.75
_RANK_SPACING = 1.0
_PAGE_MARGIN = 0.5
_RELATION_WEIGHTS: dict[RelationType, int] = {
    "flow": 4,
    "data": 3,
    "control": 4,
    "power": 5,
    "communication": 2,
    "mechanical": 1,
    "association": 1,
}


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _node_line(node: DiagramNode, *, indent: str = "  ") -> str:
    size = size_node(node)
    return (
        f"{indent}{_quote(node.id)} ["
        f"width=\"{size.width:.4f}\", "
        f"height=\"{size.height:.4f}\", "
        f"label={_quote(size.wrapped_label)}"
        "];"
    )


def build_dot(graph: DiagramGraph) -> str:
    """Serialize a semantic graph to stable DOT text."""

    rank_direction = "TB" if graph.orientation == "top_to_bottom" else "LR"
    lines = [
        "digraph visiogen {",
        (
            "  graph ["
            f'rankdir="{rank_direction}", '
            f'nodesep="{_NODE_SPACING:.4f}", '
            f'ranksep="{_RANK_SPACING:.4f}"'
            "];"
        ),
        '  node [fixedsize="true", shape="box"];',
    ]

    children_by_parent: dict[str, list[DiagramNode]] = {}
    for node in graph.nodes:
        if node.parent_id is not None:
            children_by_parent.setdefault(node.parent_id, []).append(node)

    clustered_ids = {
        child.id for children in children_by_parent.values() for child in children
    }
    clustered_ids.update(children_by_parent)
    for node in sorted(graph.nodes, key=lambda item: item.id):
        if node.id not in clustered_ids:
            lines.append(_node_line(node))

    nodes_by_id = {node.id: node for node in graph.nodes}
    for parent_id in sorted(children_by_parent):
        parent = nodes_by_id[parent_id]
        parent_label = size_node(parent).wrapped_label
        lines.extend(
            [
                f"  subgraph {_quote(f'cluster_{parent_id}')} {{",
                f"    graph [label={_quote(parent_label)}, margin=\"24.0000\"];",
            ]
        )
        for child in sorted(children_by_parent[parent_id], key=lambda item: item.id):
            lines.append(_node_line(child, indent="    "))
        lines.append("  }")

    for edge in sorted(
        graph.edges,
        key=lambda item: (item.source, item.target, item.id or ""),
    ):
        attributes = [f'weight="{_RELATION_WEIGHTS[edge.relation]}"']
        if edge.relation == "association" or edge.direction == "none":
            attributes.append('constraint="false"')
        lines.append(
            f"  {_quote(edge.source)} -> {_quote(edge.target)} "
            f"[{', '.join(attributes)}];"
        )

    lines.append("}")
    return "\n".join(lines) + "\n"


class DotRunner(Protocol):
    """Injectable subprocess boundary for Graphviz."""

    def __call__(
        self,
        command: list[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]: ...


def _run_dot(
    command: list[str],
    *,
    input: str,
    text: bool,
    capture_output: bool,
    check: bool,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input,
        text=text,
        capture_output=capture_output,
        check=check,
        timeout=timeout,
    )


def _parse_plain(output: str) -> tuple[float, float, dict[str, tuple[float, float, float, float]]]:
    graph_width = 0.0
    graph_height = 0.0
    saw_graph = False
    geometry: dict[str, tuple[float, float, float, float]] = {}
    try:
        for raw_line in output.splitlines():
            fields = shlex.split(raw_line)
            if not fields:
                continue
            if fields[0] == "graph":
                if len(fields) < 4:
                    raise ValueError("incomplete graph record")
                graph_width = float(fields[2])
                graph_height = float(fields[3])
                saw_graph = True
            elif fields[0] == "node":
                if len(fields) < 6:
                    raise ValueError("incomplete node record")
                node_id = fields[1]
                x, y, width, height = map(float, fields[2:6])
                geometry[node_id] = (
                    round(x + _PAGE_MARGIN, 4),
                    round(y + _PAGE_MARGIN, 4),
                    round(width, 4),
                    round(height, 4),
                )
    except (IndexError, ValueError) as exc:
        raise LayoutError("malformed Graphviz plain output") from exc
    if not saw_graph or graph_width <= 0 or graph_height <= 0 or not geometry:
        raise LayoutError("malformed Graphviz plain output")
    return graph_width, graph_height, geometry


def _restore_node_sizes(
    graph: DiagramGraph,
    geometry: dict[str, tuple[float, float, float, float]],
) -> None:
    nodes_by_id = {node.id: node for node in graph.nodes}
    for node_id, (x, y, _, _) in tuple(geometry.items()):
        node = nodes_by_id.get(node_id)
        if node is None:
            continue
        size = size_node(node)
        geometry[node_id] = (x, y, size.width, size.height)


class GraphvizLayout:
    """Primary deterministic layout strategy backed by ``dot -Tplain``."""

    def __init__(
        self,
        *,
        executable: str = "dot",
        timeout: float = 10.0,
        runner: DotRunner | None = None,
    ) -> None:
        self._executable = executable
        self._timeout = timeout
        self._runner = runner or _run_dot

    def layout(self, graph: DiagramGraph) -> LayoutResult:
        """Generate DOT, invoke Graphviz, and return Visio coordinates in inches."""

        try:
            completed = self._runner(
                [self._executable, "-Tplain"],
                input=build_dot(graph),
                text=True,
                capture_output=True,
                check=True,
                timeout=self._timeout,
            )
        except FileNotFoundError as exc:
            raise LayoutError(
                f"Graphviz executable '{self._executable}' was not found"
            ) from exc
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise LayoutError("Graphviz layout command failed") from exc
        graph_width, graph_height, geometry = _parse_plain(completed.stdout)
        _restore_node_sizes(graph, geometry)
        try:
            add_container_geometry(graph, geometry)
        except LayoutError as exc:
            raise LayoutError("malformed Graphviz plain output") from exc
        page = fit_page_to_geometry(
            geometry,
            margin=_PAGE_MARGIN,
            minimum_width=graph_width + 2 * _PAGE_MARGIN,
            minimum_height=graph_height + 2 * _PAGE_MARGIN,
        )
        return apply_geometry(wrapped_graph(graph), geometry, page)
