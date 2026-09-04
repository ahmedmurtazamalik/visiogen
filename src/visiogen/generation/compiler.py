"""Deterministic G4 compiler and renderer-neutral validated IR."""

from __future__ import annotations

from itertools import combinations, pairwise
from math import hypot, isclose, sqrt
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
_MIN_CONTAINER_PADDING = 0.25
_MIN_SIBLING_CLEARANCE = 0.25


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


_ELLIPTICAL_MASTERS = {"__template_connector_hub__", "__template_sensor__"}
_ROUNDED_MASTERS = {"__template_controller__", "__template_interface__"}


def _circle_radius(chord: float, sagitta: float) -> float:
    return ((chord / 2.0) ** 2 + sagitta**2) / (2.0 * sagitta)


def _note_fold(width: float, height: float) -> tuple[float, float]:
    control_y = min(0.2 * height, 2.0 * height * width**2 / (width**2 + height**2))
    control_x = min(
        max(
            0.8 * width,
            width - sqrt(max(height**2 - (height - control_y) ** 2, 0.0)),
        ),
        sqrt(max(width**2 - control_y**2, 0.0)),
    )
    delta_x = width - control_x
    distance_squared = delta_x**2 + control_y**2
    return (
        distance_squared / (2.0 * delta_x),
        distance_squared / (2.0 * control_y),
    )


def port_fractions(
    master: str,
    width: float,
    height: float,
    side: str,
    offset: float,
) -> tuple[float, float]:
    """Return a named port on the selected master's visible silhouette."""

    if side in {"top", "bottom"}:
        x_fraction = offset
        y_fraction = 1.0 if side == "top" else 0.0
    else:
        x_fraction = 1.0 if side == "right" else 0.0
        y_fraction = 1.0 - offset

    if master in _ELLIPTICAL_MASTERS:
        radial = sqrt(max(offset * (1.0 - offset), 0.0))
        if side == "left":
            x_fraction = 0.5 - radial
        elif side == "right":
            x_fraction = 0.5 + radial
        elif side == "top":
            y_fraction = 0.5 + radial
        else:
            y_fraction = 0.5 - radial
    elif master == "__template_decision__":
        radial = min(offset, 1.0 - offset)
        if side == "left":
            x_fraction = 0.5 - radial
        elif side == "right":
            x_fraction = 0.5 + radial
        elif side == "top":
            y_fraction = 0.5 + radial
        else:
            y_fraction = 0.5 - radial
    elif master == "__template_power_source__":
        left_tip = -0.07735026666667
        left_shoulder = 0.21132486666667
        right_shoulder = 0.78867513333333
        right_tip = 1.0773502666667
        shoulder = abs(1.0 - 2.0 * offset) * (left_shoulder - left_tip)
        if side == "left":
            x_fraction = left_tip + shoulder
        elif side == "right":
            x_fraction = right_tip - shoulder
        elif x_fraction < left_shoulder:
            incline = (x_fraction - left_tip) / (left_shoulder - left_tip)
            y_fraction = 0.5 + (0.5 * incline if side == "top" else -0.5 * incline)
        elif x_fraction > right_shoulder:
            incline = (right_tip - x_fraction) / (right_tip - right_shoulder)
            y_fraction = 0.5 + (0.5 * incline if side == "top" else -0.5 * incline)
    elif master == "__template_input_output__":
        slant = min(height / 4.0, width / 4.0)
        if side in {"left", "right"}:
            shift = slant * (1.0 - 2.0 * offset)
            x_fraction = (shift if side == "left" else width + shift) / width
        elif side == "top" and width * offset < slant:
            y_fraction = (width * offset + slant) / (2.0 * slant)
        elif side == "bottom" and width * offset > width - slant:
            y_fraction = (width * offset - (width - slant)) / (2.0 * slant)
    elif master == "__template_delay__":
        sagitta = min(width, height) / 2.0
        radius = _circle_radius(height, sagitta)
        center_x = width - radius
        if side == "right":
            local_y = height * y_fraction
            local_x = center_x + sqrt(
                max(radius**2 - (local_y - height / 2.0) ** 2, 0.0)
            )
            x_fraction = local_x / width
        elif side in {"top", "bottom"} and width * offset > width - sagitta:
            local_x = width * offset
            curve = sqrt(max(radius**2 - (local_x - center_x) ** 2, 0.0))
            y_fraction = (height / 2.0 + (curve if side == "top" else -curve)) / height
    elif master in _ROUNDED_MASTERS:
        radius = min(width * 0.1, width / 2.0, height / 2.0)
        if side in {"left", "right"}:
            local_y = height * y_fraction
            if local_y < radius:
                inset = radius - sqrt(max(radius**2 - (local_y - radius) ** 2, 0.0))
            elif local_y > height - radius:
                inset = radius - sqrt(
                    max(radius**2 - (local_y - (height - radius)) ** 2, 0.0)
                )
            else:
                inset = 0.0
            x_fraction = (inset if side == "left" else width - inset) / width
        else:
            local_x = width * x_fraction
            if local_x < radius:
                inset = radius - sqrt(max(radius**2 - (local_x - radius) ** 2, 0.0))
            elif local_x > width - radius:
                inset = radius - sqrt(
                    max(radius**2 - (local_x - (width - radius)) ** 2, 0.0)
                )
            else:
                inset = 0.0
            y_fraction = (height - inset if side == "top" else inset) / height
    elif master == "__template_terminator__":
        radius_fraction = min(height / (2.0 * width), 0.25)
        if side in {"left", "right"}:
            curve = sqrt(max(1.0 - (2.0 * y_fraction - 1.0) ** 2, 0.0))
            inset = radius_fraction * (1.0 - curve)
            x_fraction = inset if side == "left" else 1.0 - inset
        elif x_fraction < radius_fraction:
            curve = sqrt(
                max(
                    1.0 - ((x_fraction - radius_fraction) / radius_fraction) ** 2,
                    0.0,
                )
            )
            y_fraction = 0.5 + (0.5 * curve if side == "top" else -0.5 * curve)
        elif x_fraction > 1.0 - radius_fraction:
            curve = sqrt(
                max(
                    1.0
                    - ((x_fraction - (1.0 - radius_fraction)) / radius_fraction) ** 2,
                    0.0,
                )
            )
            y_fraction = 0.5 + (0.5 * curve if side == "top" else -0.5 * curve)
    elif master == "__template_database__":
        sagitta = min(height / 8.0, width / 8.0)
        radius = _circle_radius(height, sagitta)
        if side in {"left", "right"}:
            local_y = height * y_fraction
            curve = sqrt(
                max(radius**2 - (local_y - height / 2.0) ** 2, 0.0)
            )
            if side == "left":
                x_fraction = (radius - curve) / width
            else:
                x_fraction = (width + sagitta - radius + curve) / width
        elif width * x_fraction < sagitta:
            local_x = width * x_fraction
            curve = sqrt(max(radius**2 - (local_x - radius) ** 2, 0.0))
            y_fraction = (height / 2.0 + (curve if side == "top" else -curve)) / height
    elif master == "__template_document__":
        wave = min(min(width, height) / 8.0, width / 12.0)
        radius = _circle_radius(width / 2.0, wave)
        if side == "bottom":
            local_x = width * offset
            if local_x <= width / 2.0:
                local_y = radius - sqrt(
                    max(radius**2 - (local_x - width / 4.0) ** 2, 0.0)
                )
            else:
                local_y = 2.0 * wave - radius + sqrt(
                    max(radius**2 - (local_x - 3.0 * width / 4.0) ** 2, 0.0)
                )
            y_fraction = local_y / height
        elif side in {"left", "right"} and height * y_fraction < wave:
            local_y = height * y_fraction
            curve = sqrt(max(radius**2 - (local_y - radius) ** 2, 0.0))
            local_x = width / 4.0 + (curve if side == "right" else -curve)
            x_fraction = local_x / width
    elif master == "__template_note__":
        fold_x, fold_y = _note_fold(width, height)
        if side == "right" and height * y_fraction < fold_y:
            local_y = height * y_fraction
            x_fraction = (
                width - fold_x + fold_x * local_y / fold_y
            ) / width
        elif side == "bottom" and width * x_fraction > width - fold_x:
            local_x = width * x_fraction
            y_fraction = (
                fold_y * (local_x - (width - fold_x)) / fold_x
            ) / height
    return x_fraction, y_fraction


def _port(
    rect: Rect,
    master: str,
    side: str,
    offset: float,
) -> tuple[float, float]:
    x_fraction, y_fraction = port_fractions(
        master,
        rect.width,
        rect.height,
        side,
        offset,
    )
    return (
        rect.x + rect.width * x_fraction,
        rect.y + rect.height * (1.0 - y_fraction),
    )


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


def _outside_page_margin(
    point: Point | IRPoint,
    width: float,
    height: float,
    margin: float,
) -> bool:
    return (
        point.x < margin - _COORDINATE_TOLERANCE
        or point.y < margin - _COORDINATE_TOLERANCE
        or point.x > width - margin + _COORDINATE_TOLERANCE
        or point.y > height - margin + _COORDINATE_TOLERANCE
    )


def _rect_inside_page_margin(
    rect: Rect | IRRect,
    width: float,
    height: float,
    margin: float,
) -> bool:
    return (
        rect.x >= margin - _COORDINATE_TOLERANCE
        and rect.y >= margin - _COORDINATE_TOLERANCE
        and rect.x + rect.width <= width - margin + _COORDINATE_TOLERANCE
        and rect.y + rect.height <= height - margin + _COORDINATE_TOLERANCE
    )


def _shape_visual_bounds(
    rect: Rect | IRRect,
    master: str,
) -> tuple[float, float, float, float]:
    left = rect.x
    top = rect.y
    right = rect.x + rect.width
    bottom = rect.y + rect.height
    if master == "__template_input_output__":
        overhang = min(rect.height / 4.0, rect.width / 4.0)
        left -= overhang
        right += overhang
    elif master == "__template_power_source__":
        overhang = rect.width * 0.0773502666667
        left -= overhang
        right += overhang
    elif master == "__template_database__":
        right += min(rect.height / 8.0, rect.width / 8.0)
    return left, top, right, bottom


def _bounds_inside_page_margin(
    bounds: tuple[float, float, float, float],
    width: float,
    height: float,
    margin: float,
) -> bool:
    left, top, right, bottom = bounds
    return (
        left >= margin - _COORDINATE_TOLERANCE
        and top >= margin - _COORDINATE_TOLERANCE
        and right <= width - margin + _COORDINATE_TOLERANCE
        and bottom <= height - margin + _COORDINATE_TOLERANCE
    )


def _bounds_inside_rect(
    bounds: tuple[float, float, float, float],
    outer: Rect | IRRect,
    padding: float,
    header: float,
) -> bool:
    left, top, right, bottom = bounds
    return (
        left >= outer.x + padding - _COORDINATE_TOLERANCE
        and top >= outer.y + padding + header - _COORDINATE_TOLERANCE
        and right <= outer.x + outer.width - padding + _COORDINATE_TOLERANCE
        and bottom <= outer.y + outer.height - padding + _COORDINATE_TOLERANCE
    )


def _visual_bounds_have_clearance(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
    clearance: float,
) -> bool:
    first_left, first_top, first_right, first_bottom = first
    second_left, second_top, second_right, second_bottom = second
    horizontal_gap = max(
        first_left - second_right,
        second_left - first_right,
        0.0,
    )
    vertical_gap = max(
        first_top - second_bottom,
        second_top - first_bottom,
        0.0,
    )
    return hypot(horizontal_gap, vertical_gap) + _COORDINATE_TOLERANCE >= clearance


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
    if (
        plan.page.width <= 2 * plan.page.margin
        or plan.page.height <= 2 * plan.page.margin
    ):
        findings.append("page margin leaves no usable drawing area")
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
                    x=_port(item.rect, item.master, port.side, port.offset)[0],
                    y=_port(item.rect, item.master, port.side, port.offset)[1],
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
        if not _bounds_inside_page_margin(
            _shape_visual_bounds(item.rect, item.master_marker),
            plan.page.width,
            plan.page.height,
            plan.page.margin,
        ):
            findings.append(f"shape '{item.id}' violates the page margin")
        if item.container:
            if item.container.padding < _MIN_CONTAINER_PADDING:
                findings.append(
                    f"container '{item.object_id}' padding must be at least "
                    f"{_MIN_CONTAINER_PADDING:g} inches"
                )
            if item.rect.width <= 2.0 * item.container.padding + _COORDINATE_TOLERANCE:
                findings.append(
                    f"container '{item.object_id}' padding leaves no usable header width"
                )
            if (
                item.rect.height
                <= item.container.header_height
                + 2.0 * item.container.padding
                + _COORDINATE_TOLERANCE
            ):
                findings.append(
                    f"container '{item.object_id}' header and padding leave no usable body"
                )
            for member_id in item.container.member_ids:
                member = by_object[member_id]
                if item.container.clipping == "contain" and not _bounds_inside_rect(
                    _shape_visual_bounds(member.rect, member.master_marker),
                    item.rect,
                    item.container.padding,
                    item.container.header_height,
                ):
                    findings.append(
                        f"member '{member_id}' violates container '{item.object_id}' padding/header"
                    )

    parent_by_object = {
        item.id: item.parent_id for item in specification.objects
    }
    clearance = _MIN_SIBLING_CLEARANCE
    sibling_groups: dict[str | None, list[IRShape]] = {}
    for item in shapes:
        sibling_groups.setdefault(parent_by_object[item.object_id], []).append(item)
    for siblings in sibling_groups.values():
        for first, second in combinations(siblings, 2):
            if not _visual_bounds_have_clearance(
                _shape_visual_bounds(first.rect, first.master_marker),
                _shape_visual_bounds(second.rect, second.master_marker),
                clearance,
            ):
                findings.append(
                    f"sibling shapes '{first.id}' and '{second.id}' require at least "
                    f"{clearance:g} inches of clearance"
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
            _outside_page(point, plan.page.width, plan.page.height)
            for point in route
        ):
            findings.append(f"connector '{item.id}' route is outside page bounds")
        elif any(
            _outside_page_margin(
                point,
                plan.page.width,
                plan.page.height,
                plan.page.margin,
            )
            for point in route
        ):
            findings.append(f"connector '{item.id}' route violates the page margin")
        label_position = (
            Point(
                x=item.label.position.x,
                y=item.label.position.y - item.label.offset,
            )
            if item.label
            else None
        )
        if label_position and _outside_page(
            label_position, plan.page.width, plan.page.height
        ):
            findings.append(f"connector '{item.id}' label is outside page bounds")
        elif label_position and _outside_page_margin(
            label_position,
            plan.page.width,
            plan.page.height,
            plan.page.margin,
        ):
            findings.append(f"connector '{item.id}' label violates the page margin")
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
        elif not _rect_inside_page_margin(
            item.rect,
            plan.page.width,
            plan.page.height,
            plan.page.margin,
        ):
            findings.append(f"callout '{item.id}' violates the page margin")
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
        elif any(
            _outside_page_margin(
                point,
                plan.page.width,
                plan.page.height,
                plan.page.margin,
            )
            for point in item.leader_route
        ):
            findings.append(f"callout '{item.id}' leader violates the page margin")
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
