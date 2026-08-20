"""Hybrid AI diagram-design contract and hard validation guardrails."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from visiogen.extractor import ExtractedDiagramGraph
from visiogen.layout import LayoutResult, PageGeometry, apply_geometry
from visiogen.models import DiagramGraph
from visiogen.normalization import normalize_extracted_graph

CompositionStyle = Literal[
    "balanced_hierarchy",
    "compact_flow",
    "spacious_system",
    "contained_schematic",
    "radial",
    "custom",
]
ConnectorSide = Literal["top", "right", "bottom", "left", "auto"]
VisualImportance = Literal["primary", "secondary", "supporting"]


class DesignModel(BaseModel):
    """Strict base model for untrusted model-produced design data."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class NodePlacement(DesignModel):
    """One AI-proposed node rectangle in Visio page inches."""

    node_id: str
    x: float = Field(gt=0)
    y: float = Field(gt=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    importance: VisualImportance = "secondary"


class ConnectorHint(DesignModel):
    """Preferred connector attachment sides retained for routing work."""

    edge_id: str
    source_side: ConnectorSide = "auto"
    target_side: ConnectorSide = "auto"


class LayoutPlan(DesignModel):
    """Structured composition and complete preferred geometry."""

    composition: CompositionStyle
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    placements: list[NodePlacement]
    connector_hints: list[ConnectorHint] = Field(default_factory=list)


class DiagramDesign(DesignModel):
    """Semantic graph plus stochastic visual composition from an AI designer."""

    graph: ExtractedDiagramGraph
    layout: LayoutPlan
    rationale: str

    def normalized_graph(self) -> DiagramGraph:
        """Return canonical semantics without altering the model's design response."""

        return normalize_extracted_graph(self.graph.to_diagram_graph())

    def to_layout_result(self) -> LayoutResult:
        """Convert a validated design into the renderer's positioned contract."""

        graph = self.normalized_graph()
        geometry = {
            placement.node_id: (
                placement.x,
                placement.y,
                placement.width,
                placement.height,
            )
            for placement in self.layout.placements
        }
        return apply_geometry(
            graph,
            geometry,
            PageGeometry(
                width=self.layout.page_width,
                height=self.layout.page_height,
            ),
        ).model_copy(
            update={
                "connector_hints": {
                    hint.edge_id: (hint.source_side, hint.target_side)
                    for hint in self.layout.connector_hints
                }
            }
        )


class DesignValidationError(ValueError):
    """Raised when a schema-valid AI design violates a hard invariant."""

    def __init__(self, findings: list[str]) -> None:
        self.findings = tuple(findings)
        super().__init__("; ".join(findings))


def _bounds(placement: NodePlacement) -> tuple[float, float, float, float]:
    return (
        placement.x - placement.width / 2,
        placement.y - placement.height / 2,
        placement.x + placement.width / 2,
        placement.y + placement.height / 2,
    )


def _overlap_area(first: NodePlacement, second: NodePlacement) -> float:
    first_left, first_bottom, first_right, first_top = _bounds(first)
    second_left, second_bottom, second_right, second_top = _bounds(second)
    overlap_width = min(first_right, second_right) - max(first_left, second_left)
    overlap_height = min(first_top, second_top) - max(first_bottom, second_bottom)
    if overlap_width <= 1e-6 or overlap_height <= 1e-6:
        return 0.0
    return overlap_width * overlap_height


def validate_design(design: DiagramDesign) -> DiagramDesign:
    """Enforce mechanical invariants without replacing the AI composition."""

    graph = design.normalized_graph()
    node_ids = {node.id for node in graph.nodes}
    edge_ids = {edge.id for edge in graph.edges if edge.id is not None}
    parents = {node.id: node.parent_id for node in graph.nodes}
    placements: dict[str, NodePlacement] = {}
    findings: list[str] = []

    for placement in design.layout.placements:
        if placement.node_id in placements:
            findings.append(f"duplicate placement for node '{placement.node_id}'")
        placements[placement.node_id] = placement

    for node_id in sorted(node_ids - placements.keys()):
        findings.append(f"missing placement for node '{node_id}'")
    for node_id in sorted(placements.keys() - node_ids):
        findings.append(f"placement references unknown node '{node_id}'")

    seen_hint_ids: set[str] = set()
    for hint in design.layout.connector_hints:
        if hint.edge_id in seen_hint_ids:
            findings.append(f"Duplicate connector hint for edge '{hint.edge_id}'")
        seen_hint_ids.add(hint.edge_id)
        if hint.edge_id not in edge_ids:
            findings.append(f"connector hint references unknown edge '{hint.edge_id}'")

    page_width = design.layout.page_width
    page_height = design.layout.page_height
    for node_id in sorted(node_ids & placements.keys()):
        left, bottom, right, top = _bounds(placements[node_id])
        if left < 0 or bottom < 0 or right > page_width or top > page_height:
            findings.append(f"placement for node '{node_id}' is outside page bounds")

    ordered_ids = sorted(node_ids & placements.keys())
    for index, first_id in enumerate(ordered_ids):
        for second_id in ordered_ids[index + 1 :]:
            if parents[first_id] == second_id or parents[second_id] == first_id:
                continue
            if _overlap_area(placements[first_id], placements[second_id]) > 1e-6:
                findings.append(f"placements for nodes '{first_id}' and '{second_id}' overlap")

    for child_id, parent_id in sorted(parents.items()):
        if parent_id is None or child_id not in placements or parent_id not in placements:
            continue
        child_left, child_bottom, child_right, child_top = _bounds(placements[child_id])
        parent_left, parent_bottom, parent_right, parent_top = _bounds(placements[parent_id])
        if (
            child_left < parent_left
            or child_bottom < parent_bottom
            or child_right > parent_right
            or child_top > parent_top
        ):
            findings.append(f"placement for node '{child_id}' is outside container '{parent_id}'")

    if findings:
        raise DesignValidationError(findings)
    return design
