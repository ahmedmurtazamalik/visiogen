"""Provider-neutral extraction boundary and geometry-free DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from visiogen.models import (
    DiagramEdge,
    DiagramGraph,
    DiagramNode,
    DiagramType,
    DirectionType,
    LineStyle,
    NodeType,
    Orientation,
    RelationType,
)


class ExtractionModel(BaseModel):
    """Base model that rejects provider fields outside the extraction schema."""

    model_config = ConfigDict(extra="forbid")


class ExtractedDiagramNode(ExtractionModel):
    """A semantic node DTO that deliberately has no geometry fields."""

    id: str
    type: NodeType
    label: str
    parent_id: str | None = None
    reference_number: str | None = None
    notes: str | None = None


class ExtractedDiagramEdge(ExtractionModel):
    """A semantic edge DTO whose ID may be assigned during normalization."""

    id: str | None = None
    source: str
    target: str
    relation: RelationType = "flow"
    direction: DirectionType = "forward"
    label: str | None = None
    style: LineStyle = "solid"


class ExtractedDiagramGraph(ExtractionModel):
    """Structured provider output before canonical normalization."""

    title: str
    diagram_type: DiagramType
    orientation: Orientation
    nodes: list[ExtractedDiagramNode] = Field(default_factory=list)
    edges: list[ExtractedDiagramEdge] = Field(default_factory=list)

    def to_diagram_graph(self) -> DiagramGraph:
        """Convert extraction DTOs to the canonical graph without adding semantics."""
        return DiagramGraph(
            title=self.title,
            diagram_type=self.diagram_type,
            orientation=self.orientation,
            nodes=[DiagramNode.model_validate(node.model_dump()) for node in self.nodes],
            edges=[DiagramEdge.model_validate(edge.model_dump()) for edge in self.edges],
        )
