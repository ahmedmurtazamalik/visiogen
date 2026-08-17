"""Diagram graph normalization and cross-reference validation."""

from __future__ import annotations

from vega.models import DiagramGraph, DiagramNode

_CONTAINER_TYPES = frozenset({"housing", "subsystem"})


class GraphNormalizationError(ValueError):
    """Raised when a graph violates a canonical normalization rule."""


def _find_duplicate(values: list[str]) -> str | None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None


def _validate_containment(
    graph: DiagramGraph, nodes_by_id: dict[str, DiagramNode]
) -> None:
    for item in graph.nodes:
        if item.parent_id is None:
            continue
        if item.parent_id == item.id:
            raise GraphNormalizationError(f"node '{item.id}' cannot contain itself")
        parent = nodes_by_id.get(item.parent_id)
        if parent is None:
            raise GraphNormalizationError(
                f"node '{item.id}' references missing parent '{item.parent_id}'"
            )
        if parent.type not in _CONTAINER_TYPES:
            raise GraphNormalizationError(
                f"parent '{item.parent_id}' is not container-capable"
            )

    for item in graph.nodes:
        visited = {item.id}
        parent_id = item.parent_id
        while parent_id is not None:
            if parent_id in visited:
                raise GraphNormalizationError(
                    f"containment cycle detected from node '{item.id}'"
                )
            visited.add(parent_id)
            parent = nodes_by_id[parent_id]
            parent_id = parent.parent_id

    for item in graph.nodes:
        if item.parent_id is None:
            continue
        parent = nodes_by_id[item.parent_id]
        if parent.parent_id is not None:
            raise GraphNormalizationError(
                f"node '{item.id}' exceeds the baseline one level of containment"
            )


def _assign_edge_ids(graph: DiagramGraph) -> None:
    used_ids = {item.id for item in graph.edges if item.id}
    next_number = 1
    for item in graph.edges:
        if item.id:
            continue
        while f"e{next_number}" in used_ids:
            next_number += 1
        item.id = f"e{next_number}"
        used_ids.add(item.id)
        next_number += 1


def normalize_graph(graph: DiagramGraph) -> DiagramGraph:
    """Return a validated, normalized deep copy without inventing semantics."""
    normalized = graph.model_copy(deep=True)

    duplicate_node = _find_duplicate([item.id for item in normalized.nodes])
    if duplicate_node is not None:
        raise GraphNormalizationError(f"duplicate node ID '{duplicate_node}'")

    explicit_edge_ids = [item.id for item in normalized.edges if item.id]
    duplicate_edge = _find_duplicate(explicit_edge_ids)
    if duplicate_edge is not None:
        raise GraphNormalizationError(f"duplicate edge ID '{duplicate_edge}'")

    nodes_by_id = {item.id: item for item in normalized.nodes}
    for item in normalized.edges:
        if item.source not in nodes_by_id:
            raise GraphNormalizationError(
                f"edge source '{item.source}' does not reference an existing node"
            )
        if item.target not in nodes_by_id:
            raise GraphNormalizationError(
                f"edge target '{item.target}' does not reference an existing node"
            )

    _validate_containment(normalized, nodes_by_id)

    reference_numbers: set[str] = set()
    for item in normalized.nodes:
        if item.reference_number is None:
            continue
        normalized_reference = item.reference_number.strip()
        if not normalized_reference:
            continue
        if normalized_reference in reference_numbers:
            raise GraphNormalizationError(
                f"duplicate reference number '{normalized_reference}'"
            )
        reference_numbers.add(normalized_reference)

    _assign_edge_ids(normalized)
    return normalized


def normalize_extracted_graph(graph: DiagramGraph) -> DiagramGraph:
    """Normalize provider output while enforcing the no-geometry boundary."""
    if graph.has_geometry:
        raise GraphNormalizationError(
            "extracted graph must not contain layout geometry"
        )
    return normalize_graph(graph)
