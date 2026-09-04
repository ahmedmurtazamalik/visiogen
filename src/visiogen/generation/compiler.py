"""Deterministic G4 compiler and renderer-neutral validated IR."""

from __future__ import annotations

from itertools import pairwise
from math import isclose
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from visiogen.design import DiagramDesign, validate_design
from visiogen.generation.construction import (
    ConnectorPlan,
    Point,
    Rect,
    VisioConstructionPlan,
    validate_construction_plan,
)
from visiogen.generation.specification import DiagramSpecification
from visiogen.shape_mapper import map_edge_visual, map_node_visual

_MASTER_NAMES = {
    "__template_terminator__": "Terminator",
    "__template_process__": "Process",
    "__template_decision__": "Decision",
    "__template_input_output__": "Data",
    "__template_database__": "Database",
    "__template_document__": "Document",
    "__template_predefined_process__": "Predefined Process",
    "__template_delay__": "Delay",
    "__template_note__": "Note",
    "__template_connector_hub__": "On-page Reference",
    "__template_component_rectangle__": "Rectangle",
    "__template_subsystem_container__": "Subsystem",
    "__template_controller__": "Controller",
    "__template_sensor__": "Sensor",
    "__template_power_source__": "Power Source",
    "__template_interface__": "Interface",
    "__template_external_system__": "External System",
    "__template_housing_container__": "Housing",
    "__template_connector__": "Dynamic Connector",
    "__template_reference_callout__": "Reference Callout",
}
_COORDINATE_TOLERANCE = 1e-9


class IRModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)


class IRPoint(IRModel):
    x: float
    y: float


class IRRect(IRModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class IRPage(IRModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    orientation: Literal["portrait", "landscape"]
    margin: float
    grid: float


class IRRegion(IRModel):
    id: str
    name: str
    rect: IRRect


class IRGuide(IRModel):
    id: str
    axis: Literal["horizontal", "vertical"]
    position: float


class IRTypography(IRModel):
    family: Literal["Arial", "Calibri", "Aptos"]
    size_pt: float
    bold: bool
    italic: bool
    color: str
    horizontal_align: Literal["left", "center", "right"]
    vertical_align: Literal["top", "middle", "bottom"]


class IRShapeStyle(IRModel):
    fill_color: str
    line_color: str
    line_weight_pt: float
    line_pattern: Literal["solid", "dashed", "dotted"]


class IRConnectorStyle(IRModel):
    line_color: str
    line_weight_pt: float
    line_pattern: Literal["solid", "dashed", "dotted"]


class IRContainer(IRModel):
    header_text: str
    header_height: float
    padding: float
    member_ids: tuple[str, ...]
    clipping: Literal["contain", "allow_overflow"]


class IRPort(IRModel):
    name: str
    side: Literal["top", "right", "bottom", "left"]
    x: float
    y: float


class IRShape(IRModel):
    id: str
    object_id: str
    text: str
    master_marker: str
    master_name: str
    rect: IRRect
    text_box: IRRect
    typography: IRTypography
    style: IRShapeStyle
    z_order: int
    ports: tuple[IRPort, ...]
    container: IRContainer | None


class IRConnector(IRModel):
    id: str
    relationship_id: str
    source_shape_id: str
    source_port: str
    target_shape_id: str
    target_port: str
    master_marker: str
    master_name: str
    connector_type: Literal["dynamic", "straight", "orthogonal", "polyline"]
    route: tuple[IRPoint, ...]
    bends: tuple[IRPoint, ...]
    jumps: bool
    arrowheads: Literal["none", "begin", "end", "both"]
    style: IRConnectorStyle
    label: IRConnectorLabel | None
    z_order: int


class IRCallout(IRModel):
    id: str
    object_id: str
    master_marker: str
    master_name: str
    text: str
    rect: IRRect
    target_anchor: IRPoint
    leader_route: tuple[IRPoint, ...]
    z_order: int


class IRConnectorLabel(IRModel):
    text: str
    position: IRPoint
    offset: float
    orientation: Literal["horizontal", "along_route"]
    background: Literal["none", "opaque"]


class RendererIR(IRModel):
    version: Literal[1] = 1
    source_engine: Literal["v1_compatibility", "v2"]
    page: IRPage
    regions: tuple[IRRegion, ...]
    guides: tuple[IRGuide, ...]
    shapes: tuple[IRShape, ...]
    connectors: tuple[IRConnector, ...]
    callouts: tuple[IRCallout, ...]


class CompilationError(ValueError):
    def __init__(self, findings: list[str]) -> None:
        self.findings = tuple(findings)
        super().__init__("; ".join(findings))


def _port(rect: Rect, side: str, offset: float) -> tuple[float, float]:
    if side == "top":
        return rect.x + rect.width * offset, rect.y
    if side == "right":
        return rect.x + rect.width, rect.y + rect.height * offset
    if side == "bottom":
        return rect.x + rect.width * offset, rect.y + rect.height
    return rect.x, rect.y + rect.height * offset


def _inside(
    point: Point | IRPoint, rect: Rect | IRRect, *, clearance: float = 0.0
) -> bool:
    return (
        rect.x - clearance <= point.x <= rect.x + rect.width + clearance
        and rect.y - clearance <= point.y <= rect.y + rect.height + clearance
    )


def _rect_inside(
    inner: Rect | IRRect,
    outer: Rect | IRRect,
    padding: float = 0.0,
    header: float = 0.0,
) -> bool:
    return (
        inner.x >= outer.x + padding
        and inner.y >= outer.y + padding + header
        and inner.x + inner.width <= outer.x + outer.width - padding
        and inner.y + inner.height <= outer.y + outer.height - padding
    )


def _rects_overlap(
    first: Rect | IRRect, second: Rect | IRRect, clearance: float = 0.0
) -> bool:
    return not (
        first.x + first.width + clearance <= second.x
        or second.x + second.width + clearance <= first.x
        or first.y + first.height + clearance <= second.y
        or second.y + second.height + clearance <= first.y
    )


def _segment_intersects_rect(
    first: Point | IRPoint, second: Point | IRPoint, rect: Rect | IRRect
) -> bool:
    """Return whether a finite segment touches or enters an axis-aligned rectangle."""

    minimum_x, maximum_x = sorted((first.x, second.x))
    minimum_y, maximum_y = sorted((first.y, second.y))
    if (
        maximum_x < rect.x
        or minimum_x > rect.x + rect.width
        or maximum_y < rect.y
        or minimum_y > rect.y + rect.height
    ):
        return False
    delta_x = second.x - first.x
    delta_y = second.y - first.y
    entry, exit_ = 0.0, 1.0
    for numerator, denominator in (
        (first.x - rect.x, -delta_x),
        (rect.x + rect.width - first.x, delta_x),
        (first.y - rect.y, -delta_y),
        (rect.y + rect.height - first.y, delta_y),
    ):
        if denominator == 0:
            if numerator < 0:
                return False
            continue
        parameter = numerator / denominator
        if denominator < 0:
            entry = max(entry, parameter)
        else:
            exit_ = min(exit_, parameter)
        if entry > exit_:
            return False
    return True


def _outside_page(point: Point | IRPoint, width: float, height: float) -> bool:
    return point.x < 0 or point.y < 0 or point.x > width or point.y > height


def _same_point(first: Point | IRPoint, second: Point | IRPoint) -> bool:
    return first.x == second.x and first.y == second.y


def _same_coordinate(first: float, second: float) -> bool:
    return isclose(first, second, rel_tol=0, abs_tol=_COORDINATE_TOLERANCE)


def _resolved_route(
    connector: ConnectorPlan, shapes: dict[str, IRShape]
) -> tuple[IRPoint, ...]:
    source = next(
        port
        for port in shapes[connector.source_shape_id].ports
        if port.name == connector.source_port
    )
    target = next(
        port
        for port in shapes[connector.target_shape_id].ports
        if port.name == connector.target_port
    )
    return (
        IRPoint(x=source.x, y=source.y),
        *(IRPoint.model_validate(point.model_dump()) for point in connector.waypoints),
        IRPoint(x=target.x, y=target.y),
    )


def compile_construction_plan(
    specification: DiagramSpecification,
    plan: VisioConstructionPlan,
) -> RendererIR:
    """Compile without repair or aesthetic inference; reject every impossible plan."""

    validate_construction_plan(specification, plan)
    findings: list[str] = []
    object_text = {item.id: item.label for item in specification.objects}
    shapes = tuple(
        IRShape(
            id=item.id,
            object_id=item.object_id,
            text=object_text[item.object_id],
            master_marker=item.master,
            master_name=_MASTER_NAMES[item.master],
            rect=IRRect.model_validate(item.rect.model_dump()),
            text_box=IRRect.model_validate(item.text_box.model_dump()),
            typography=IRTypography.model_validate(item.typography.model_dump()),
            style=IRShapeStyle(
                fill_color=item.style.fill_color.upper(),
                line_color=item.style.line_color.upper(),
                line_weight_pt=item.style.line_weight_pt,
                line_pattern=item.style.line_pattern,
            ),
            z_order=item.z_order,
            ports=tuple(
                IRPort(
                    name=port.name,
                    side=port.side,
                    x=_port(item.rect, port.side, port.offset)[0],
                    y=_port(item.rect, port.side, port.offset)[1],
                )
                for port in item.ports
            ),
            container=IRContainer.model_validate(item.container.model_dump())
            if item.container
            else None,
        )
        for item in plan.shapes
    )
    by_id = {item.id: item for item in shapes}
    by_object = {item.object_id: item for item in shapes}

    element_ids = [
        *(item.id for item in plan.regions),
        *(item.id for item in plan.guides),
        *(item.id for item in plan.shapes),
        *(item.id for item in plan.connectors),
        *(item.id for item in plan.callouts),
    ]
    duplicate_ids = sorted(
        identifier
        for identifier in set(element_ids)
        if element_ids.count(identifier) > 1
    )
    if duplicate_ids:
        findings.append("plan element IDs must be unique: " + ", ".join(duplicate_ids))
    for region in plan.regions:
        if (
            region.rect.x + region.rect.width > plan.page.width
            or region.rect.y + region.rect.height > plan.page.height
        ):
            findings.append(f"region '{region.id}' is outside page bounds")

    for plan_shape, item in zip(plan.shapes, shapes, strict=True):
        port_names = [port.name for port in plan_shape.ports]
        if len(port_names) != len(set(port_names)):
            findings.append(f"shape '{item.id}' port names must be unique")
        if not _rect_inside(item.text_box, item.rect):
            findings.append(f"shape '{item.id}' text box is outside its shape")
        if item.container:
            for member_id in item.container.member_ids:
                member = by_object[member_id]
                if item.container.clipping == "contain" and not _rect_inside(
                    member.rect,
                    item.rect,
                    item.container.padding,
                    item.container.header_height,
                ):
                    findings.append(
                        f"member '{member_id}' violates container '{item.object_id}' padding/header"
                    )

    connectors: list[IRConnector] = []
    for index, item in enumerate(plan.connectors):
        route = _resolved_route(item, by_id)
        if any(_same_point(first, second) for first, second in pairwise(route)):
            findings.append(
                f"connector '{item.id}' route contains a zero-length segment"
            )
        if item.connector_type == "straight" and len(route) != 2:
            findings.append(
                f"connector '{item.id}' straight route cannot have waypoints"
            )
        if item.connector_type == "orthogonal":
            for first, second in pairwise(route):
                if not _same_coordinate(first.x, second.x) and not _same_coordinate(
                    first.y, second.y
                ):
                    findings.append(
                        f"connector '{item.id}' has a non-orthogonal segment"
                    )
        if any(
            _outside_page(point, plan.page.width, plan.page.height) for point in route
        ):
            findings.append(f"connector '{item.id}' route is outside page bounds")
        if item.label and _outside_page(
            item.label.position, plan.page.width, plan.page.height
        ):
            findings.append(f"connector '{item.id}' label is outside page bounds")
        excluded = {item.source_shape_id, item.target_shape_id}
        for shape in shapes:
            if shape.id in excluded or shape.container is not None:
                continue
            if any(_inside(point, shape.rect) for point in item.waypoints):
                findings.append(
                    f"connector '{item.id}' waypoint intersects unrelated shape "
                    f"'{shape.id}'"
                )
            if any(
                _segment_intersects_rect(a, b, shape.rect) for a, b in pairwise(route)
            ):
                findings.append(
                    f"connector '{item.id}' intersects unrelated shape '{shape.id}'"
                )
            if any(
                _segment_intersects_rect(a, b, shape.text_box)
                for a, b in pairwise(route)
            ):
                findings.append(
                    f"connector '{item.id}' intersects unrelated label '{shape.id}'"
                )
        connectors.append(
            IRConnector(
                id=item.id,
                relationship_id=item.relationship_id,
                source_shape_id=item.source_shape_id,
                source_port=item.source_port,
                target_shape_id=item.target_shape_id,
                target_port=item.target_port,
                master_marker=item.master,
                master_name=_MASTER_NAMES[item.master],
                connector_type=item.connector_type,
                route=route,
                bends=tuple(
                    IRPoint.model_validate(point.model_dump())
                    for point in item.bends
                ),
                jumps=item.jumps,
                arrowheads=item.arrowheads,
                style=IRConnectorStyle(
                    line_color=item.line_color.upper(),
                    line_weight_pt=item.line_weight_pt,
                    line_pattern=item.line_pattern,
                ),
                label=IRConnectorLabel.model_validate(item.label.model_dump())
                if item.label
                else None,
                z_order=max((shape.z_order for shape in shapes), default=0) + index + 1,
            )
        )

    callouts: list[IRCallout] = []
    for item in plan.callouts:
        if (
            item.rect.x + item.rect.width > plan.page.width
            or item.rect.y + item.rect.height > plan.page.height
        ):
            findings.append(f"callout '{item.id}' is outside page bounds")
        if not _inside(item.leader_route[0], item.rect):
            findings.append(f"callout '{item.id}' leader does not start at its callout")
        if not _same_point(item.leader_route[-1], item.target_anchor):
            findings.append(
                f"callout '{item.id}' leader does not end at its target anchor"
            )
        if any(
            _outside_page(point, plan.page.width, plan.page.height)
            for point in item.leader_route
        ):
            findings.append(f"callout '{item.id}' leader is outside page bounds")
        if any(
            _same_point(first, second) for first, second in pairwise(item.leader_route)
        ):
            findings.append(
                f"callout '{item.id}' leader contains a zero-length segment"
            )
        for shape in shapes:
            if (
                shape.object_id != item.object_id
                and shape.container is None
                and _rects_overlap(item.rect, shape.rect)
            ):
                findings.append(
                    f"callout '{item.id}' overlaps unrelated shape '{shape.id}'"
                )
            if (
                shape.object_id != item.object_id
                and shape.container is None
                and any(
                    _segment_intersects_rect(first, second, shape.rect)
                    for first, second in pairwise(item.leader_route)
                )
            ):
                findings.append(
                    f"callout '{item.id}' leader intersects unrelated shape "
                    f"'{shape.id}'"
                )
            if (
                shape.object_id != item.object_id
                and shape.container is None
                and any(
                    _segment_intersects_rect(first, second, shape.text_box)
                    for first, second in pairwise(item.leader_route)
                )
            ):
                findings.append(
                    f"callout '{item.id}' leader intersects unrelated label '{shape.id}'"
                )
        if not _inside(item.target_anchor, by_object[item.object_id].rect):
            findings.append(f"callout '{item.id}' target anchor is outside its object")
        callouts.append(
            IRCallout(
                id=item.id,
                object_id=item.object_id,
                master_marker=item.carrier,
                master_name=_MASTER_NAMES[item.carrier],
                text=item.text,
                rect=IRRect.model_validate(item.rect.model_dump()),
                target_anchor=IRPoint.model_validate(item.target_anchor.model_dump()),
                leader_route=tuple(
                    IRPoint.model_validate(point.model_dump())
                    for point in item.leader_route
                ),
                z_order=item.z_order,
            )
        )
    for index, first in enumerate(plan.callouts):
        for second in plan.callouts[index + 1 :]:
            if _rects_overlap(first.rect, second.rect):
                findings.append(f"callouts '{first.id}' and '{second.id}' overlap")
    if findings:
        raise CompilationError(findings)
    return RendererIR(
        source_engine="v2",
        page=IRPage.model_validate(plan.page.model_dump()),
        regions=tuple(
            IRRegion.model_validate(item.model_dump()) for item in plan.regions
        ),
        guides=tuple(IRGuide.model_validate(item.model_dump()) for item in plan.guides),
        shapes=tuple(sorted(shapes, key=lambda item: (item.z_order, item.id))),
        connectors=tuple(connectors),
        callouts=tuple(sorted(callouts, key=lambda item: (item.z_order, item.id))),
    )


def compile_v1_design(design: DiagramDesign) -> RendererIR:
    """Expose the existing V1 deterministic mapping as an explicitly tagged IR."""

    layout = validate_design(design).to_layout_result()
    shapes = []
    for index, node in enumerate(layout.graph.nodes):
        visual = map_node_visual(node.type)
        assert node.x is not None
        assert node.y is not None
        assert node.width is not None
        assert node.height is not None
        rect = IRRect(
            x=node.x - node.width / 2,
            y=node.y - node.height / 2,
            width=node.width,
            height=node.height,
        )
        shapes.append(
            IRShape(
                id=f"shape_{node.id}",
                object_id=node.id,
                text=node.label,
                master_marker=visual.marker,
                master_name=_MASTER_NAMES[visual.marker],
                rect=rect,
                text_box=rect,
                typography=IRTypography(
                    family="Arial",
                    size_pt=10.0,
                    bold=False,
                    italic=False,
                    color="#000000",
                    horizontal_align="center",
                    vertical_align="middle",
                ),
                style=IRShapeStyle(
                    fill_color="#FFFFFF",
                    line_color="#000000",
                    line_weight_pt=1.0,
                    line_pattern="solid",
                ),
                z_order=index,
                ports=(),
                container=None,
            )
        )
    edges = []
    by_object = {item.object_id: item for item in shapes}
    for index, edge in enumerate(layout.graph.edges):
        visual = map_edge_visual(edge.relation, edge.direction, line_style=edge.style)
        source = by_object[edge.source].rect
        target = by_object[edge.target].rect
        route = (
            IRPoint(x=source.x + source.width / 2, y=source.y + source.height / 2),
            IRPoint(x=target.x + target.width / 2, y=target.y + target.height / 2),
        )
        edges.append(
            IRConnector(
                id=f"connector_{edge.id or index}",
                relationship_id=edge.id or f"edge_{index}",
                source_shape_id=f"shape_{edge.source}",
                source_port="dynamic",
                target_shape_id=f"shape_{edge.target}",
                target_port="dynamic",
                master_marker=visual.marker,
                master_name=_MASTER_NAMES[visual.marker],
                connector_type="dynamic",
                route=route,
                bends=(),
                jumps=False,
                arrowheads="both"
                if visual.begin_arrow and visual.end_arrow
                else "begin"
                if visual.begin_arrow
                else "end"
                if visual.end_arrow
                else "none",
                style=IRConnectorStyle(
                    line_color="#000000",
                    line_weight_pt=visual.line_weight,
                    line_pattern=visual.line_style,
                ),
                label=IRConnectorLabel(
                    text=edge.label,
                    position=IRPoint(
                        x=(route[0].x + route[-1].x) / 2,
                        y=(route[0].y + route[-1].y) / 2,
                    ),
                    offset=0,
                    orientation="horizontal",
                    background="none",
                )
                if edge.label
                else None,
                z_order=len(shapes) + index,
            )
        )
    return RendererIR(
        source_engine="v1_compatibility",
        page=IRPage(
            width=layout.page.width,
            height=layout.page.height,
            orientation="landscape"
            if layout.page.width >= layout.page.height
            else "portrait",
            margin=0,
            grid=1,
        ),
        regions=(),
        guides=(),
        shapes=tuple(shapes),
        connectors=tuple(edges),
        callouts=(),
    )
