"""Strict AI-authored Visio construction plan and G3 contract validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from visiogen.generation.specification import DiagramSpecification

ShapeMaster = Literal[
    "__template_terminator__", "__template_process__", "__template_decision__",
    "__template_input_output__", "__template_database__", "__template_document__",
    "__template_predefined_process__", "__template_delay__", "__template_note__",
    "__template_connector_hub__", "__template_component_rectangle__",
    "__template_subsystem_container__", "__template_controller__",
    "__template_sensor__", "__template_power_source__", "__template_interface__",
    "__template_external_system__", "__template_housing_container__",
]
Side = Literal["top", "right", "bottom", "left"]


class ConstructionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Point(ConstructionModel):
    x: float
    y: float


class Rect(ConstructionModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class PagePlan(ConstructionModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    orientation: Literal["portrait", "landscape"]
    margin: float = Field(ge=0)
    grid: float = Field(gt=0)


class RegionPlan(ConstructionModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    rect: Rect


class GuidePlan(ConstructionModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    axis: Literal["horizontal", "vertical"]
    position: float = Field(ge=0)


class Typography(ConstructionModel):
    family: Literal["Arial", "Calibri", "Aptos"]
    size_pt: float = Field(ge=8, le=36)
    bold: bool = False
    italic: bool = False
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    horizontal_align: Literal["left", "center", "right"] = "center"
    vertical_align: Literal["top", "middle", "bottom"] = "middle"


class ShapeStyle(ConstructionModel):
    fill_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    line_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    line_weight_pt: float = Field(gt=0, le=8)
    line_pattern: Literal["solid", "dashed", "dotted"] = "solid"


class PortPlan(ConstructionModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    side: Side
    offset: float = Field(ge=0, le=1)


class ContainerPlan(ConstructionModel):
    header_text: str = Field(min_length=1)
    header_height: float = Field(gt=0)
    padding: float = Field(ge=0)
    member_ids: list[str]
    clipping: Literal["contain", "allow_overflow"] = "contain"


class ShapePlan(ConstructionModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    object_id: str
    master: ShapeMaster
    rect: Rect
    text_box: Rect
    typography: Typography
    style: ShapeStyle
    z_order: int = Field(ge=0)
    ports: list[PortPlan] = Field(min_length=1)
    container: ContainerPlan | None = None


class ConnectorLabel(ConstructionModel):
    text: str = Field(min_length=1)
    position: Point
    offset: float = Field(ge=0)
    orientation: Literal["horizontal", "along_route"]
    background: Literal["none", "opaque"]


class ConnectorPlan(ConstructionModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    relationship_id: str
    master: Literal["__template_connector__"]
    connector_type: Literal["dynamic", "straight", "orthogonal", "polyline"]
    source_shape_id: str
    source_port: str
    target_shape_id: str
    target_port: str
    waypoints: list[Point]
    bends: list[Point]
    jumps: bool
    arrowheads: Literal["none", "begin", "end", "both"]
    line_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    line_weight_pt: float = Field(gt=0, le=8)
    line_pattern: Literal["solid", "dashed", "dotted"]
    label: ConnectorLabel | None = None


class CalloutPlan(ConstructionModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    object_id: str
    carrier: Literal["__template_reference_callout__"]
    text: str = Field(min_length=1)
    rect: Rect
    target_anchor: Point
    leader_route: list[Point] = Field(min_length=2)
    z_order: int = Field(ge=0)


class ConstraintTrace(ConstructionModel):
    requirement_id: str
    plan_element_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class VisioConstructionPlan(ConstructionModel):
    version: Literal[1] = 1
    specification_version: Literal[1]
    page: PagePlan
    regions: list[RegionPlan] = Field(default_factory=list)
    guides: list[GuidePlan] = Field(default_factory=list)
    shapes: list[ShapePlan] = Field(min_length=1)
    connectors: list[ConnectorPlan] = Field(default_factory=list)
    callouts: list[CalloutPlan] = Field(default_factory=list)
    traceability: list[ConstraintTrace] = Field(default_factory=list)
    visual_rationale: str = Field(min_length=1)


class ConstructionPlanError(ValueError):
    def __init__(self, findings: list[str]) -> None:
        self.findings = tuple(findings)
        super().__init__("; ".join(findings))


def validate_construction_plan(
    specification: DiagramSpecification,
    plan: VisioConstructionPlan,
) -> VisioConstructionPlan:
    """Enforce completeness, references, semantics, and coarse page bounds."""

    findings: list[str] = []
    object_ids = {item.id for item in specification.objects}
    relationship_ids = {item.id for item in specification.relationships}
    shape_by_object = {item.object_id: item for item in plan.shapes}
    if len(shape_by_object) != len(plan.shapes):
        findings.append("every specification object requires exactly one shape")
    missing_objects = object_ids - shape_by_object.keys()
    unknown_objects = shape_by_object.keys() - object_ids
    if missing_objects:
        findings.append("missing shapes for objects: " + ", ".join(sorted(missing_objects)))
    if unknown_objects:
        findings.append("shapes reference unknown objects: " + ", ".join(sorted(unknown_objects)))

    connector_by_relationship = {item.relationship_id: item for item in plan.connectors}
    if len(connector_by_relationship) != len(plan.connectors):
        findings.append("every specification relationship requires exactly one connector")
    missing_relationships = relationship_ids - connector_by_relationship.keys()
    unknown_relationships = connector_by_relationship.keys() - relationship_ids
    if missing_relationships:
        findings.append(
            "missing connectors for relationships: " + ", ".join(sorted(missing_relationships))
        )
    if unknown_relationships:
        findings.append(
            "connectors reference unknown relationships: "
            + ", ".join(sorted(unknown_relationships))
        )

    shape_ids = {item.id for item in plan.shapes}
    if len(shape_ids) != len(plan.shapes):
        findings.append("shape IDs must be unique")
    port_names = {item.id: {port.name for port in item.ports} for item in plan.shapes}
    relationship_by_id = {item.id: item for item in specification.relationships}
    expected_arrows = {"forward": "end", "reverse": "begin", "bidirectional": "both", "none": "none"}
    for connector in plan.connectors:
        if connector.source_shape_id not in shape_ids or connector.target_shape_id not in shape_ids:
            findings.append(f"connector '{connector.id}' references unknown shapes")
            continue
        if connector.source_port not in port_names[connector.source_shape_id]:
            findings.append(f"connector '{connector.id}' references unknown source port")
        if connector.target_port not in port_names[connector.target_shape_id]:
            findings.append(f"connector '{connector.id}' references unknown target port")
        relationship = relationship_by_id.get(connector.relationship_id)
        if relationship is not None:
            source = shape_by_object.get(relationship.source)
            target = shape_by_object.get(relationship.target)
            if source and connector.source_shape_id != source.id:
                findings.append(f"connector '{connector.id}' has the wrong source shape")
            if target and connector.target_shape_id != target.id:
                findings.append(f"connector '{connector.id}' has the wrong target shape")
            if connector.arrowheads != expected_arrows[relationship.direction]:
                findings.append(f"connector '{connector.id}' arrowheads contradict direction")
            if relationship.label and (connector.label is None or connector.label.text != relationship.label):
                findings.append(f"connector '{connector.id}' does not preserve its exact label")

    for shape in plan.shapes:
        for name, rect in (("shape", shape.rect), ("text box", shape.text_box)):
            if rect.x + rect.width > plan.page.width or rect.y + rect.height > plan.page.height:
                findings.append(f"{name} for '{shape.id}' is outside page bounds")
    for guide in plan.guides:
        maximum = plan.page.height if guide.axis == "horizontal" else plan.page.width
        if guide.position > maximum:
            findings.append(f"guide '{guide.id}' is outside page bounds")

    parents = {item.id: item.parent_id for item in specification.objects}
    for object_id, parent_id in parents.items():
        if parent_id is None or parent_id not in shape_by_object:
            continue
        container = shape_by_object[parent_id].container
        if container is None or object_id not in container.member_ids:
            findings.append(f"container for '{parent_id}' omits member '{object_id}'")
    for shape in plan.shapes:
        if shape.container is not None and set(shape.container.member_ids) - object_ids:
            findings.append(f"container '{shape.id}' references unknown members")

    callout_objects = [item.object_id for item in plan.callouts]
    for item in specification.objects:
        if item.reference_number is not None and callout_objects.count(item.id) != 1:
            findings.append(f"object '{item.id}' requires exactly one reference callout")
    for callout in plan.callouts:
        source = next((item for item in specification.objects if item.id == callout.object_id), None)
        if source is None:
            findings.append(f"callout '{callout.id}' references an unknown object")
        elif source.reference_number is None:
            findings.append(
                f"callout '{callout.id}' must be omitted because object "
                f"'{source.id}' has no reference number"
            )
        elif callout.text != source.reference_number:
            findings.append(f"callout '{callout.id}' does not preserve its reference number")

    trace_ids = {item.requirement_id for item in plan.traceability}
    required_traces = {
        item.id for item in specification.constraints if item.strength == "hard"
    } | {item.id for item in specification.visual_requirements}
    if required_traces - trace_ids:
        findings.append(
            "missing constraint traceability: " + ", ".join(sorted(required_traces - trace_ids))
        )
    element_ids = shape_ids | {item.id for item in plan.connectors} | {
        item.id for item in plan.callouts
    } | {item.id for item in plan.regions} | {item.id for item in plan.guides}
    for trace in plan.traceability:
        if set(trace.plan_element_ids) - element_ids:
            findings.append(f"trace '{trace.requirement_id}' references unknown plan elements")
    if findings:
        raise ConstructionPlanError(findings)
    return plan
