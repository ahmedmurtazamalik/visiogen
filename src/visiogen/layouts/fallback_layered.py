"""Deterministic layered fallback layout."""

from __future__ import annotations

from collections import defaultdict

from visiogen.layout import (
    LayoutError,
    LayoutResult,
    PageGeometry,
    add_container_geometry,
    apply_geometry,
    fit_page_to_geometry,
    size_node,
    wrapped_graph,
)
from visiogen.models import DiagramGraph, DiagramNode

_NODE_SPACING = 0.75
_RANK_SPACING = 1.0
_PAGE_MARGIN = 0.5


def _directed_pairs(graph: DiagramGraph, node_ids: set[str]) -> list[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for edge in graph.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        if edge.relation == "association" or edge.direction == "none":
            continue
        source, target = edge.source, edge.target
        if edge.direction == "reverse":
            source, target = target, source
        pairs.add((source, target))
        if edge.direction == "bidirectional":
            pairs.add((target, source))
    return sorted(pairs)


def _strongly_connected_components(
    node_ids: set[str], adjacency: dict[str, set[str]]
) -> list[tuple[str, ...]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node_id: str) -> None:
        nonlocal index
        indices[node_id] = index
        lowlinks[node_id] = index
        index += 1
        stack.append(node_id)
        on_stack.add(node_id)

        for target in sorted(adjacency[node_id]):
            if target not in indices:
                visit(target)
                lowlinks[node_id] = min(lowlinks[node_id], lowlinks[target])
            elif target in on_stack:
                lowlinks[node_id] = min(lowlinks[node_id], indices[target])

        if lowlinks[node_id] == indices[node_id]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node_id:
                    break
            components.append(tuple(sorted(component)))

    for node_id in sorted(node_ids):
        if node_id not in indices:
            visit(node_id)
    return sorted(components)


def _ranks(graph: DiagramGraph, nodes: list[DiagramNode]) -> dict[str, int]:
    node_ids = {node.id for node in nodes}
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for source, target in _directed_pairs(graph, node_ids):
        adjacency[source].add(target)

    components = _strongly_connected_components(node_ids, adjacency)
    component_by_node = {
        node_id: component_index
        for component_index, component in enumerate(components)
        for node_id in component
    }
    component_adjacency: dict[int, set[int]] = {
        index: set() for index in range(len(components))
    }
    indegree = {index: 0 for index in range(len(components))}
    for source, targets in adjacency.items():
        source_component = component_by_node[source]
        for target in targets:
            target_component = component_by_node[target]
            if (
                source_component != target_component
                and target_component not in component_adjacency[source_component]
            ):
                component_adjacency[source_component].add(target_component)
                indegree[target_component] += 1

    component_ranks = {index: 0 for index in range(len(components))}
    ready = sorted(index for index, degree in indegree.items() if degree == 0)
    while ready:
        source = ready.pop(0)
        for target in sorted(component_adjacency[source]):
            component_ranks[target] = max(
                component_ranks[target], component_ranks[source] + 1
            )
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()
    return {
        node_id: component_ranks[component_by_node[node_id]] for node_id in node_ids
    }


def _top_to_bottom_geometry(
    nodes: list[DiagramNode], ranks: dict[str, int]
) -> tuple[dict[str, tuple[float, float, float, float]], PageGeometry]:
    grouped: dict[int, list[DiagramNode]] = defaultdict(list)
    for node in nodes:
        grouped[ranks[node.id]].append(node)
    for group in grouped.values():
        group.sort(key=lambda node: node.id)

    rank_widths: dict[int, float] = {}
    rank_heights: dict[int, float] = {}
    for rank, group in grouped.items():
        sizes = [size_node(node) for node in group]
        rank_widths[rank] = sum(size.width for size in sizes) + _NODE_SPACING * (
            len(sizes) - 1
        )
        rank_heights[rank] = max(size.height for size in sizes)

    ordered_ranks = sorted(grouped)
    content_width = max(rank_widths.values())
    content_height = sum(rank_heights.values()) + _RANK_SPACING * (
        len(ordered_ranks) - 1
    )
    page = PageGeometry(
        width=round(content_width + 2 * _PAGE_MARGIN, 4),
        height=round(content_height + 2 * _PAGE_MARGIN, 4),
    )

    geometry: dict[str, tuple[float, float, float, float]] = {}
    top = page.height - _PAGE_MARGIN
    for rank in ordered_ranks:
        rank_height = rank_heights[rank]
        y = top - rank_height / 2
        left = _PAGE_MARGIN + (content_width - rank_widths[rank]) / 2
        for node in grouped[rank]:
            size = size_node(node)
            x = left + size.width / 2
            geometry[node.id] = (
                round(x, 4),
                round(y, 4),
                size.width,
                size.height,
            )
            left += size.width + _NODE_SPACING
        top -= rank_height + _RANK_SPACING
    return geometry, page


def _left_to_right_geometry(
    nodes: list[DiagramNode], ranks: dict[str, int]
) -> tuple[dict[str, tuple[float, float, float, float]], PageGeometry]:
    grouped: dict[int, list[DiagramNode]] = defaultdict(list)
    for node in nodes:
        grouped[ranks[node.id]].append(node)
    for group in grouped.values():
        group.sort(key=lambda node: node.id)

    rank_widths: dict[int, float] = {}
    rank_heights: dict[int, float] = {}
    for rank, group in grouped.items():
        sizes = [size_node(node) for node in group]
        rank_widths[rank] = max(size.width for size in sizes)
        rank_heights[rank] = sum(size.height for size in sizes) + _NODE_SPACING * (
            len(sizes) - 1
        )

    ordered_ranks = sorted(grouped)
    content_width = sum(rank_widths.values()) + _RANK_SPACING * (
        len(ordered_ranks) - 1
    )
    content_height = max(rank_heights.values())
    page = PageGeometry(
        width=round(content_width + 2 * _PAGE_MARGIN, 4),
        height=round(content_height + 2 * _PAGE_MARGIN, 4),
    )

    geometry: dict[str, tuple[float, float, float, float]] = {}
    left = _PAGE_MARGIN
    for rank in ordered_ranks:
        rank_width = rank_widths[rank]
        x = left + rank_width / 2
        top = _PAGE_MARGIN + (content_height + rank_heights[rank]) / 2
        for node in grouped[rank]:
            size = size_node(node)
            y = top - size.height / 2
            geometry[node.id] = (
                round(x, 4),
                round(y, 4),
                size.width,
                size.height,
            )
            top -= size.height + _NODE_SPACING
        left += rank_width + _RANK_SPACING
    return geometry, page


class FallbackLayeredLayout:
    """Small deterministic layered layout requiring no external executable."""

    def layout(self, graph: DiagramGraph) -> LayoutResult:
        """Position nodes with fixed spacing and stable ID tie-breaking."""

        if not graph.nodes:
            raise LayoutError("layout requires at least one node")
        container_ids = {
            node.parent_id for node in graph.nodes if node.parent_id is not None
        }
        nodes = sorted(
            (node for node in graph.nodes if node.id not in container_ids),
            key=lambda node: node.id,
        )
        ranks = _ranks(graph, nodes)
        if graph.orientation == "top_to_bottom":
            geometry, _ = _top_to_bottom_geometry(nodes, ranks)
        else:
            geometry, _ = _left_to_right_geometry(nodes, ranks)
        add_container_geometry(graph, geometry)
        page = fit_page_to_geometry(geometry, margin=_PAGE_MARGIN)
        return apply_geometry(wrapped_graph(graph), geometry, page)
