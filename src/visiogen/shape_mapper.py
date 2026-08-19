"""Deterministic semantic-to-visual template mapping."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Collection, Mapping, get_args

from visiogen.models import DirectionType, LineStyle, NodeType, RelationType

CONNECTOR_MARKER = "__template_connector__"

PRODUCTION_TEMPLATE_MARKERS = frozenset(
    {
        "__template_terminator__",
        "__template_process__",
        "__template_decision__",
        "__template_input_output__",
        "__template_database__",
        "__template_document__",
        "__template_predefined_process__",
        "__template_delay__",
        "__template_note__",
        "__template_connector_hub__",
        "__template_component_rectangle__",
        "__template_subsystem_container__",
        "__template_controller__",
        "__template_sensor__",
        "__template_power_source__",
        "__template_interface__",
        "__template_external_system__",
        "__template_housing_container__",
        "__template_reference_callout__",
        CONNECTOR_MARKER,
    }
)


class ShapeMappingError(ValueError):
    """Raised when semantic data cannot resolve to the canonical palette."""


@dataclass(frozen=True, slots=True)
class NodeVisualSpec:
    """Immutable template and default sizing for one semantic node type."""

    marker: str
    default_width: float
    default_height: float
    container_capable: bool = False


@dataclass(frozen=True, slots=True)
class EdgeVisualSpec:
    """Immutable connector appearance derived from relation and direction."""

    marker: str
    line_style: LineStyle
    line_weight: float
    begin_arrow: bool
    end_arrow: bool


def _node(
    marker: str,
    width: float,
    height: float,
    *,
    container: bool = False,
) -> NodeVisualSpec:
    return NodeVisualSpec(
        marker=f"__template_{marker}__",
        default_width=width,
        default_height=height,
        container_capable=container,
    )


_NODE_VISUALS: dict[NodeType, NodeVisualSpec] = {
    "terminator": _node("terminator", 2.6, 0.9),
    "process": _node("process", 2.625, 0.75),
    "decision": _node("decision", 2.3, 1.5),
    "input_output": _node("input_output", 3.0, 1.1),
    "data_store": _node("database", 2.5, 1.35),
    "document": _node("document", 2.7, 1.15),
    "predefined_process": _node("predefined_process", 3.0, 1.0),
    "delay": _node("delay", 2.5, 1.1),
    "note": _node("note", 2.7, 1.2),
    "connector_hub": _node("connector_hub", 1.35, 1.35),
    "component": _node("component_rectangle", 3.75, 1.0),
    "subsystem": _node("subsystem_container", 5.5, 2.8, container=True),
    "controller": _node("controller", 3.0, 1.1),
    "processor": _node("controller", 3.0, 1.1),
    "memory": _node("database", 2.5, 1.35),
    "database": _node("database", 2.5, 1.35),
    "sensor": _node("sensor", 1.8, 1.8),
    "actuator": _node("component_rectangle", 3.75, 1.0),
    "transducer": _node("sensor", 1.8, 1.8),
    "power_source": _node("power_source", 2.9, 1.4),
    "communication_module": _node("component_rectangle", 3.75, 1.0),
    "interface": _node("interface", 3.0, 0.5625),
    "external_system": _node("external_system", 3.2, 1.25),
    "service": _node("external_system", 3.2, 1.25),
    "housing": _node("housing_container", 6.5, 3.0, container=True),
}
NODE_VISUALS: Mapping[NodeType, NodeVisualSpec] = MappingProxyType(_NODE_VISUALS)

_RELATION_DEFAULTS: Mapping[RelationType, tuple[LineStyle, float]] = MappingProxyType(
    {
        "flow": ("solid", 1.0),
        "data": ("solid", 1.0),
        "control": ("solid", 1.25),
        "power": ("solid", 2.0),
        "communication": ("solid", 1.0),
        "mechanical": ("dashed", 1.0),
        "association": ("dotted", 1.0),
    }
)

_DIRECTION_ARROWS: Mapping[DirectionType, tuple[bool, bool]] = MappingProxyType(
    {
        "forward": (False, True),
        "reverse": (True, False),
        "bidirectional": (True, True),
        "none": (False, False),
    }
)


def _require_marker(marker: str, available_markers: Collection[str]) -> None:
    if marker not in available_markers:
        raise ShapeMappingError(f"Template inventory is missing marker '{marker}'")


def map_node_visual(
    node_type: NodeType,
    *,
    available_markers: Collection[str] = PRODUCTION_TEMPLATE_MARKERS,
) -> NodeVisualSpec:
    """Resolve a semantic node type to an explicit canonical template spec."""

    try:
        visual = NODE_VISUALS[node_type]
    except KeyError as exc:
        raise ShapeMappingError(f"Unknown node type '{node_type}'") from exc
    _require_marker(visual.marker, available_markers)
    return visual


def map_edge_visual(
    relation: RelationType,
    direction: DirectionType,
    *,
    line_style: LineStyle | None = None,
    available_markers: Collection[str] = PRODUCTION_TEMPLATE_MARKERS,
) -> EdgeVisualSpec:
    """Resolve relation, direction, and optional style into connector appearance."""

    try:
        default_style, line_weight = _RELATION_DEFAULTS[relation]
    except KeyError as exc:
        raise ShapeMappingError(f"Unknown relation type '{relation}'") from exc
    try:
        begin_arrow, end_arrow = _DIRECTION_ARROWS[direction]
    except KeyError as exc:
        raise ShapeMappingError(f"Unknown direction '{direction}'") from exc
    if line_style is not None and line_style not in get_args(LineStyle):
        raise ShapeMappingError(f"Unknown line style '{line_style}'")

    _require_marker(CONNECTOR_MARKER, available_markers)
    return EdgeVisualSpec(
        marker=CONNECTOR_MARKER,
        line_style=line_style or default_style,
        line_weight=line_weight,
        begin_arrow=begin_arrow,
        end_arrow=end_arrow,
    )
