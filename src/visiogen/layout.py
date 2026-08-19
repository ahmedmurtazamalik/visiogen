"""Deterministic layout contracts and shared geometry helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import textwrap

from pydantic import BaseModel, ConfigDict, Field

from visiogen.models import DiagramGraph, DiagramNode
from visiogen.shape_mapper import map_node_visual

NodeGeometry = tuple[float, float, float, float]


class LayoutError(RuntimeError):
    """Raised when deterministic layout cannot produce valid geometry."""


@dataclass(frozen=True, slots=True)
class NodeSize:
    """Deterministic text and dimensions for a positioned node."""

    width: float
    height: float
    wrapped_label: str


def size_node(node: DiagramNode) -> NodeSize:
    """Wrap a label and return deterministic bounded visual-family dimensions."""

    visual = map_node_visual(node.type)
    wrap_width = 48 if visual.container_capable else 30
    lines = textwrap.wrap(
        node.label,
        width=wrap_width,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [""]
    max_width = 7.5 if visual.container_capable else 5.0
    max_height = 4.0 if visual.container_capable else 3.0
    measured_width = max(len(line) for line in lines) * 0.11 + 0.6
    reference_reserve = 0.3 if node.reference_number else 0.0
    measured_height = len(lines) * 0.28 + 0.36 + reference_reserve
    minimum_height = visual.default_height + reference_reserve
    return NodeSize(
        width=round(min(max(visual.default_width, measured_width), max_width), 4),
        height=round(min(max(minimum_height, measured_height), max_height), 4),
        wrapped_label="\n".join(lines),
    )


def wrapped_graph(graph: DiagramGraph) -> DiagramGraph:
    """Return a deep copy with deterministic visual line breaks."""

    prepared = graph.model_copy(deep=True)
    for node in prepared.nodes:
        node.label = size_node(node).wrapped_label
    return prepared


def add_container_geometry(
    graph: DiagramGraph,
    geometry: dict[str, NodeGeometry],
) -> None:
    """Add one-level container boxes around already-positioned children."""

    children_by_parent: dict[str, list[str]] = {}
    for node in graph.nodes:
        if node.parent_id is not None:
            children_by_parent.setdefault(node.parent_id, []).append(node.id)
    nodes_by_id = {node.id: node for node in graph.nodes}
    for parent_id in sorted(children_by_parent):
        try:
            boxes = [geometry[node_id] for node_id in children_by_parent[parent_id]]
        except KeyError as exc:
            raise LayoutError(f"missing child geometry for container '{parent_id}'") from exc
        left = min(x - width / 2 for x, _, width, _ in boxes) - 0.5
        right = max(x + width / 2 for x, _, width, _ in boxes) + 0.5
        bottom = min(y - height / 2 for _, y, _, height in boxes) - 0.5
        top = max(y + height / 2 for _, y, _, height in boxes) + 0.9
        minimum = size_node(nodes_by_id[parent_id])
        geometry[parent_id] = (
            round((left + right) / 2, 4),
            round((bottom + top) / 2, 4),
            round(max(right - left, minimum.width), 4),
            round(max(top - bottom, minimum.height), 4),
        )


def fit_page_to_geometry(
    geometry: dict[str, NodeGeometry],
    *,
    margin: float = 0.5,
    minimum_width: float = 0.0,
    minimum_height: float = 0.0,
) -> PageGeometry:
    """Shift boxes inside a margin and return a page enclosing every box."""

    left = min(x - width / 2 for x, _, width, _ in geometry.values())
    bottom = min(y - height / 2 for _, y, _, height in geometry.values())
    shift_x = max(0.0, margin - left)
    shift_y = max(0.0, margin - bottom)
    if shift_x or shift_y:
        for node_id, (x, y, width, height) in tuple(geometry.items()):
            geometry[node_id] = (
                round(x + shift_x, 4),
                round(y + shift_y, 4),
                width,
                height,
            )
    right = max(x + width / 2 for x, _, width, _ in geometry.values())
    top = max(y + height / 2 for _, y, _, height in geometry.values())
    return PageGeometry(
        width=round(max(minimum_width, right + margin), 4),
        height=round(max(minimum_height, top + margin), 4),
    )


class PageGeometry(BaseModel):
    """Final Visio page dimensions in inches."""

    model_config = ConfigDict(frozen=True)

    width: float = Field(gt=0)
    height: float = Field(gt=0)


class LayoutResult(BaseModel):
    """A positioned graph and its final page geometry."""

    model_config = ConfigDict(frozen=True)

    graph: DiagramGraph
    page: PageGeometry


def apply_geometry(
    graph: DiagramGraph,
    geometry_by_id: Mapping[str, NodeGeometry],
    page: PageGeometry,
) -> LayoutResult:
    """Return a positioned deep copy while preserving the semantic input graph."""

    node_ids = {node.id for node in graph.nodes}
    geometry_ids = set(geometry_by_id)
    missing = sorted(node_ids - geometry_ids)
    if missing:
        raise LayoutError(f"missing geometry for node(s): {', '.join(missing)}")
    unknown = sorted(geometry_ids - node_ids)
    if unknown:
        raise LayoutError(f"geometry references unknown node(s): {', '.join(unknown)}")
    for node_id, box in geometry_by_id.items():
        if any(value <= 0 for value in box):
            raise LayoutError(f"positive geometry required for node '{node_id}'")
        x, y, width, height = box
        if (
            x - width / 2 < 0
            or y - height / 2 < 0
            or x + width / 2 > page.width
            or y + height / 2 > page.height
        ):
            raise LayoutError(f"geometry outside page for node '{node_id}'")

    positioned = graph.model_copy(deep=True)
    for node in positioned.nodes:
        x, y, width, height = geometry_by_id[node.id]
        node.x = x
        node.y = y
        node.width = width
        node.height = height
    return LayoutResult(graph=positioned, page=page)
