"""Canonical diagram data models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DiagramType = Literal["flowchart", "system_block", "component_schematic"]
Orientation = Literal["top_to_bottom", "left_to_right"]
NodeType = Literal[
    "terminator",
    "process",
    "decision",
    "input_output",
    "data_store",
    "document",
    "predefined_process",
    "delay",
    "note",
    "connector_hub",
    "component",
    "subsystem",
    "controller",
    "processor",
    "memory",
    "database",
    "sensor",
    "actuator",
    "transducer",
    "power_source",
    "communication_module",
    "interface",
    "external_system",
    "service",
    "housing",
]
RelationType = Literal[
    "flow",
    "data",
    "control",
    "power",
    "communication",
    "mechanical",
    "association",
]
DirectionType = Literal["forward", "reverse", "bidirectional", "none"]
LineStyle = Literal["solid", "dashed", "dotted"]


class DiagramNode(BaseModel):
    """A semantic diagram element with optional post-layout geometry."""

    id: str
    type: NodeType
    label: str
    parent_id: str | None = None
    reference_number: str | None = None
    notes: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None


class DiagramEdge(BaseModel):
    """A typed relationship between two diagram nodes."""

    id: str | None = None
    source: str
    target: str
    relation: RelationType = "flow"
    direction: DirectionType = "forward"
    label: str | None = None
    style: LineStyle = "solid"


class DiagramGraph(BaseModel):
    """The authoritative semantic graph shared by pipeline stages."""

    title: str
    diagram_type: DiagramType
    orientation: Orientation
    nodes: list[DiagramNode] = Field(default_factory=list)
    edges: list[DiagramEdge] = Field(default_factory=list)

    @property
    def has_geometry(self) -> bool:
        """Return whether any node contains layout geometry."""
        geometry_fields = ("x", "y", "width", "height")
        return any(
            getattr(node, field) is not None
            for node in self.nodes
            for field in geometry_fields
        )
