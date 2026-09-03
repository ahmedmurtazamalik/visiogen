"""G5 native RendererIR structural tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import pytest
from vsdx import Shape, VisioFile, namespace

from visiogen.generation.compiler import (
    IRCallout,
    IRConnector,
    IRConnectorLabel,
    IRConnectorStyle,
    IRContainer,
    IRPage,
    IRPoint,
    IRPort,
    IRRect,
    IRShape,
    IRShapeStyle,
    IRTypography,
    RendererIR,
)
from visiogen.renderer import render_ir
from visiogen.validation import validate_vsdx_package

TEMPLATE = Path("templates/template.vsdx")


def _outer(shape: Shape) -> Shape:
    current = shape
    while isinstance(current.parent, Shape) and current.parent.ID is not None:
        current = current.parent
    return current


def _shape(
    identifier: str,
    text: str,
    marker: str,
    rect: tuple[float, float, float, float],
    z_order: int,
    *,
    container: IRContainer | None = None,
) -> IRShape:
    x, y, width, height = rect
    return IRShape(
        id=identifier,
        object_id=identifier.removeprefix("shape_"),
        text=text,
        master_marker=marker,
        master_name=text,
        rect=IRRect(x=x, y=y, width=width, height=height),
        text_box=IRRect(x=x, y=y, width=width, height=height),
        typography=IRTypography(
            family="Arial",
            size_pt=11,
            bold=True,
            italic=False,
            color="#123456",
            horizontal_align="center",
            vertical_align="middle",
        ),
        style=IRShapeStyle(
            fill_color="#EEF4FF",
            line_color="#234567",
            line_weight_pt=1.5,
            line_pattern="solid",
        ),
        z_order=z_order,
        ports=(
            IRPort(name="top", side="top", x=x + width / 2, y=y),
            IRPort(name="right", side="right", x=x + width, y=y + height / 2),
            IRPort(name="bottom", side="bottom", x=x + width / 2, y=y + height),
            IRPort(name="left", side="left", x=x, y=y + height / 2),
        ),
        container=container,
    )


def _connector(
    identifier: str,
    source: str,
    source_port: str,
    target: str,
    target_port: str,
    route: tuple[tuple[float, float], ...],
    z_order: int,
    *,
    connector_type: Literal[
        "dynamic", "straight", "orthogonal", "polyline"
    ] = "polyline",
    label: str | None = None,
) -> IRConnector:
    points = tuple(IRPoint(x=x, y=y) for x, y in route)
    return IRConnector(
        id=identifier,
        relationship_id=identifier,
        source_shape_id=source,
        source_port=source_port,
        target_shape_id=target,
        target_port=target_port,
        master_marker="__template_connector__",
        master_name="Dynamic Connector",
        connector_type=connector_type,
        route=points,
        bends=points[1:-1],
        jumps=True,
        arrowheads="end",
        style=IRConnectorStyle(
            line_color="#345678", line_weight_pt=2, line_pattern="dashed"
        ),
        label=IRConnectorLabel(
            text=label,
            position=points[len(points) // 2],
            offset=0.1,
            orientation="horizontal",
            background="opaque",
        )
        if label
        else None,
        z_order=z_order,
    )


def _comprehensive_ir() -> RendererIR:
    outer = _shape(
        "shape_outer",
        "Outer",
        "__template_housing_container__",
        (0.5, 0.5, 8.5, 6.5),
        0,
        container=IRContainer(
            header_text="Outer",
            header_height=0.4,
            padding=0.2,
            member_ids=("inner",),
            clipping="contain",
        ),
    )
    inner = _shape(
        "shape_inner",
        "Inner",
        "__template_subsystem_container__",
        (1, 1.2, 7.5, 5.3),
        1,
        container=IRContainer(
            header_text="Inner",
            header_height=0.4,
            padding=0.2,
            member_ids=("a", "b", "c"),
            clipping="contain",
        ),
    )
    a = _shape("shape_a", "A", "__template_process__", (1.5, 2, 1.5, 1), 2)
    b = _shape("shape_b", "B", "__template_process__", (5.5, 2, 1.5, 1), 3)
    c = _shape("shape_c", "C", "__template_decision__", (3.5, 4.5, 1.5, 1), 4)
    connectors = (
        _connector(
            "horizontal",
            "shape_a",
            "right",
            "shape_b",
            "left",
            ((3, 2.5), (5.5, 2.5)),
            10,
            label="horizontal",
        ),
        _connector(
            "vertical",
            "shape_a",
            "bottom",
            "shape_c",
            "top",
            ((2.25, 3), (2.25, 4), (4.25, 4), (4.25, 4.5)),
            11,
        ),
        _connector(
            "diagonal",
            "shape_b",
            "bottom",
            "shape_c",
            "right",
            ((6.25, 3), (5, 4), (5, 5)),
            12,
        ),
        _connector(
            "reciprocal",
            "shape_b",
            "left",
            "shape_a",
            "top",
            ((5.5, 2.5), (4, 1.5), (2.25, 2)),
            13,
        ),
        _connector(
            "self_loop",
            "shape_c",
            "right",
            "shape_c",
            "bottom",
            ((5, 5), (5.5, 5), (5.5, 6), (4.25, 5.5)),
            14,
        ),
        _connector(
            "dynamic",
            "shape_a",
            "top",
            "shape_b",
            "top",
            ((2.25, 2), (6.25, 2)),
            15,
            connector_type="dynamic",
        ),
    )
    return RendererIR(
        source_engine="v2",
        page=IRPage(width=10, height=8, orientation="landscape", margin=0.5, grid=0.25),
        regions=(),
        guides=(),
        shapes=(outer, inner, a, b, c),
        connectors=connectors,
        callouts=(
            IRCallout(
                id="callout_a",
                object_id="a",
                master_marker="__template_reference_callout__",
                master_name="Reference Callout",
                text="101",
                rect=IRRect(x=1.5, y=3.3, width=0.8, height=0.35),
                target_anchor=IRPoint(x=2.25, y=3),
                leader_route=(IRPoint(x=1.9, y=3.3), IRPoint(x=2.25, y=3)),
                z_order=20,
            ),
        ),
    )


def test_render_ir_preserves_native_structure_routes_ports_and_callouts(
    tmp_path: Path,
) -> None:
    output = tmp_path / "generation-v2.vsdx"
    source_hash = hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()

    assert render_ir(TEMPLATE, _comprehensive_ir(), output) == output
    validate_vsdx_package(output)
    assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == source_hash

    with VisioFile(str(output)) as document:
        page = document.get_page_by_name("Template Palette")
        assert (page.width, page.height) == pytest.approx((10, 8))
        assert not any(
            shape.text.strip().startswith("__template_") for shape in page.all_shapes
        )
        shape_a = _outer(page.find_shape_by_text("A"))
        assert (shape_a.x, shape_a.y, shape_a.width, shape_a.height) == pytest.approx(
            (2.25, 5.5, 1.5, 1)
        )
        assert shape_a.cell_value("FillForegnd") == "#EEF4FF"
        assert shape_a.cell_value("LineColor") == "#234567"
        ports = shape_a.xml.find(f"{namespace}Section[@N='Connection']")
        assert {row.attrib["N"] for row in ports} == {"top", "right", "bottom", "left"}

        horizontal = _outer(page.find_shape_by_text("horizontal"))
        rows = horizontal.xml.findall(
            f"{namespace}Section[@N='Geometry'][@IX='0']/{namespace}Row"
        )
        assert [row.attrib["T"] for row in rows] == ["MoveTo", "LineTo"]
        assert horizontal.cell_value("LinePattern") == "2"
        assert horizontal.cell_value("EndArrow") == "4"
        assert horizontal.cell_value("TextBkgnd") == "#FFFFFF"
        connection_cells = {
            item.xml.attrib["FromCell"]: item.xml.attrib["ToCell"]
            for item in page.connects
            if item.from_id == horizontal.ID
        }
        assert connection_cells == {
            "BeginX": "Connections.right",
            "EndX": "Connections.left",
        }
        connectors = {}
        for connection in page.connects:
            connectors.setdefault(connection.from_id, {})[
                connection.xml.attrib["FromCell"]
            ] = connection.xml.attrib["ToSheet"]
        assert len(connectors) == 6
        assert (
            sum(
                endpoints.get("BeginX") == shape_a.ID
                for endpoints in connectors.values()
            )
            == 3
        )
        shape_c = _outer(page.find_shape_by_text("C"))
        assert any(
            endpoints == {"BeginX": shape_c.ID, "EndX": shape_c.ID}
            for endpoints in connectors.values()
        )

        dynamic_id = next(
            item.from_id
            for item in page.connects
            if item.xml.attrib["ToCell"] == "Connections.top"
            and item.xml.attrib["FromCell"] == "BeginX"
        )
        dynamic = next(shape for shape in page.all_shapes if dynamic_id == shape.ID)
        assert (
            dynamic.cell_formula("BeginX")
            == "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
        )

        outer = _outer(page.find_shape_by_text("Outer"))
        inner = _outer(page.find_shape_by_text("Inner"))
        inner_label = page.find_shape_by_text("Inner")
        assert float(inner_label.cell_value("TxtHeight")) == pytest.approx(0.4)
        assert f"Sheet.{outer.ID}!SheetRef()" in inner.cell_formula("Relationships")
        assert f"Sheet.{inner.ID}!SheetRef()" in shape_a.cell_formula("Relationships")

        callout = _outer(page.find_shape_by_text("101"))
        assert f"Sheet.{shape_a.ID}!SheetRef()" in callout.cell_formula("Relationships")
        leader_rows = callout.xml.findall(
            f"{namespace}Section[@N='Geometry'][@IX='0']/{namespace}Row"
        )
        assert [row.attrib["T"] for row in leader_rows] == ["MoveTo", "LineTo"]


def test_render_ir_keeps_requested_z_order(tmp_path: Path) -> None:
    output = render_ir(TEMPLATE, _comprehensive_ir(), tmp_path / "z-order.vsdx")

    with VisioFile(str(output)) as document:
        page = document.get_page_by_name("Template Palette")
        labels = [
            next(
                (
                    child.text.strip()
                    for child in shape.all_shapes
                    if child.text.strip()
                ),
                shape.text.strip(),
            )
            for shape in page.child_shapes
        ]

    assert labels[:5] == ["Outer", "Inner", "A", "B", "C"]
    assert labels[-1] == "101"
