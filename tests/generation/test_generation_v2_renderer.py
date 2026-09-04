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
    port_fractions,
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
            position=IRPoint(
                x=(points[0].x + points[-1].x) / 2,
                y=(points[0].y + points[-1].y) / 2,
            ),
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
            connector_type="straight",
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
            connector_type="orthogonal",
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


def professional_acceptance_ir() -> RendererIR:
    housing = _shape(
        "shape_housing",
        "Signal Processing System",
        "__template_housing_container__",
        (0.5, 0.6, 10, 5.8),
        0,
        container=IRContainer(
            header_text="Signal Processing System",
            header_height=0.45,
            padding=0.35,
            member_ids=("sensor", "controller", "database"),
            clipping="contain",
        ),
    )
    sensor = _shape(
        "shape_sensor", "Sensor", "__template_sensor__", (1.25, 2.4, 1.8, 1.4), 1
    )
    controller = _shape(
        "shape_controller",
        "Controller",
        "__template_controller__",
        (4.35, 2.35, 2.3, 1.5),
        2,
    )
    database = _shape(
        "shape_database",
        "Event Store",
        "__template_database__",
        (7.85, 2.4, 1.9, 1.4),
        3,
    )
    sensor_data = _connector(
        "sensor_data",
        "shape_sensor",
        "right",
        "shape_controller",
        "left",
        ((3.05, 3.1), (4.35, 3.1)),
        10,
        connector_type="dynamic",
        label="sensor data",
    )
    event_stream = _connector(
        "event_stream",
        "shape_controller",
        "right",
        "shape_database",
        "left",
        ((6.65, 3.1), (7.85, 3.1)),
        11,
        connector_type="dynamic",
        label="event stream",
    )
    return RendererIR(
        source_engine="v2",
        page=IRPage(width=11, height=7, orientation="landscape", margin=0.4, grid=0.25),
        regions=(),
        guides=(),
        shapes=(housing, sensor, controller, database),
        connectors=(sensor_data, event_stream),
        callouts=(
            IRCallout(
                id="callout_sensor",
                object_id="sensor",
                master_marker="__template_reference_callout__",
                master_name="Reference Callout",
                text="110",
                rect=IRRect(x=1.65, y=4.25, width=0.8, height=0.35),
                target_anchor=IRPoint(x=2.15, y=3.8),
                leader_route=(
                    IRPoint(x=2.05, y=4.25),
                    IRPoint(x=2.15, y=3.8),
                ),
                z_order=20,
            ),
            IRCallout(
                id="callout_controller",
                object_id="controller",
                master_marker="__template_reference_callout__",
                master_name="Reference Callout",
                text="120",
                rect=IRRect(x=5.1, y=4.25, width=0.8, height=0.35),
                target_anchor=IRPoint(x=5.5, y=3.85),
                leader_route=(
                    IRPoint(x=5.5, y=4.25),
                    IRPoint(x=5.5, y=3.85),
                ),
                z_order=21,
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
        assert shape_a.xml.find(f"{namespace}Section[@N='Geometry']") is None
        ports = shape_a.xml.find(f"{namespace}Section[@N='Connection']")
        assert {row.attrib["N"] for row in ports} == {"top", "right", "bottom", "left"}
        port_rows = {row.attrib["N"]: row for row in ports}
        assert port_rows["top"].find(
            f"{namespace}Cell[@N='X']"
        ).attrib["F"] == "Width*0.5"
        assert port_rows["top"].find(
            f"{namespace}Cell[@N='Y']"
        ).attrib["F"] == "Height*1"
        assert port_rows["right"].find(
            f"{namespace}Cell[@N='X']"
        ).attrib["F"] == "Width*1"
        assert port_rows["bottom"].find(
            f"{namespace}Cell[@N='Y']"
        ).attrib["F"] == "Height*0"
        assert port_rows["left"].find(
            f"{namespace}Cell[@N='X']"
        ).attrib["F"] == "Width*0"
        directions = {
            row.attrib["N"]: (
                row.find(f"{namespace}Cell[@N='DirX']").attrib["V"],
                row.find(f"{namespace}Cell[@N='DirY']").attrib["V"],
            )
            for row in ports
        }
        assert directions == {
            "top": ("0", "-1"),
            "right": ("-1", "0"),
            "bottom": ("0", "1"),
            "left": ("1", "0"),
        }

        horizontal = _outer(page.find_shape_by_text("horizontal"))
        rows = horizontal.xml.findall(
            f"{namespace}Section[@N='Geometry'][@IX='0']/{namespace}Row"
        )
        assert [row.attrib["T"] for row in rows if row.attrib.get("Del") != "1"] == [
            "MoveTo",
            "LineTo",
        ]
        assert any(row.attrib.get("Del") == "1" for row in rows)
        assert horizontal.cell_value("LinePattern") == "2"
        assert horizontal.cell_value("EndArrow") == "4"
        assert horizontal.cell_value("TextBkgnd") == "#FFFFFF"
        shape_b = _outer(page.find_shape_by_text("B"))
        assert horizontal.cell_formula("BeginX") == (
            f"PAR(PNT(Sheet.{shape_a.ID}!Connections.right.X,"
            f"Sheet.{shape_a.ID}!Connections.right.Y))"
        )
        assert horizontal.cell_formula("EndX") == (
            f"PAR(PNT(Sheet.{shape_b.ID}!Connections.left.X,"
            f"Sheet.{shape_b.ID}!Connections.left.Y))"
        )
        assert "BeginX" in horizontal.cell_formula("PinX")
        assert "EndX" in horizontal.cell_formula("PinX")
        assert rows[0].find(f"{namespace}Cell[@N='X']").attrib["F"] == (
            "BeginX-PinX+LocPinX"
        )
        assert rows[1].find(f"{namespace}Cell[@N='X']").attrib["F"] == (
            "EndX-PinX+LocPinX"
        )
        assert horizontal.cell_value("ConFixedCode") == "0"
        assert horizontal.cell_value("ShapeRouteStyle") == "2"
        assert horizontal.cell_value("ConLineRouteExt") == "1"
        assert horizontal.xml.find(f"{namespace}Cell[@N='RouteStyle']") is None
        assert horizontal.cells["TxtPinX"].xml.attrib["F"] == "No Formula"
        vertical_id = next(
            item.from_id
            for item in page.connects
            if item.xml.attrib["ToCell"] == "Connections.bottom"
            and item.xml.attrib["FromCell"] == "BeginX"
        )
        vertical = next(shape for shape in page.all_shapes if shape.ID == vertical_id)
        vertical_rows = vertical.xml.findall(
            f"{namespace}Section[@N='Geometry'][@IX='0']/{namespace}Row"
        )
        assert vertical.cell_value("ConFixedCode") == "0"
        assert vertical.cell_value("ShapeRouteStyle") == "1"
        assert vertical.cell_value("ConLineRouteExt") == "0"
        assert vertical_rows[1].find(f"{namespace}Cell[@N='X']").attrib["F"] == (
            "BeginX-PinX+LocPinX"
        )
        assert vertical_rows[-2].find(f"{namespace}Cell[@N='X']").attrib["F"] == (
            "EndX-PinX+LocPinX"
        )
        connection_cells = {
            item.xml.attrib["FromCell"]: item.xml.attrib["ToCell"]
            for item in page.connects
            if item.from_id == horizontal.ID
        }
        assert connection_cells == {
            "BeginX": "Connections.right",
            "EndX": "Connections.left",
        }
        shapes_by_id = {shape.ID: shape for shape in page.all_shapes}
        for connection in page.connects:
            to_cell = connection.xml.attrib["ToCell"]
            if not to_cell.startswith("Connections."):
                continue
            target = shapes_by_id[connection.to_id]
            port_name = to_cell.removeprefix("Connections.")
            section = target.xml.find(f"{namespace}Section[@N='Connection']")
            assert section is not None
            rows = [
                row
                for row in section.findall(f"{namespace}Row")
                if row.attrib.get("Del") != "1"
            ]
            local_index = next(
                index
                for index, row in enumerate(rows)
                if row.attrib.get("N") == port_name
            )
            master_section = target.master_shape.xml.find(
                f"{namespace}Section[@N='Connection']"
            )
            inherited_count = (
                sum(
                    row.attrib.get("Del") != "1"
                    for row in master_section.findall(f"{namespace}Row")
                )
                if master_section is not None
                else 0
            )
            assert connection.xml.attrib["ToPart"] == str(
                100 + inherited_count + local_index
            )
        connectors = {}
        for connection in page.connects:
            connectors.setdefault(connection.from_id, {})[
                connection.xml.attrib["FromCell"]
            ] = connection.xml.attrib["ToSheet"]
        assert len(connectors) == 6
        for connector_id in connectors:
            connector_shape = next(
                shape for shape in page.all_shapes if shape.ID == connector_id
            )
            inherited_caches = [
                cell
                for section in connector_shape.xml.findall(f"{namespace}Section")
                if section.attrib.get("N")
                in {"Geometry", "Scratch", "Control", "User"}
                for cell in section.iter(f"{namespace}Cell")
                if cell.attrib.get("F") == "Inh"
            ]
            assert inherited_caches == []
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

        dynamic = next(
            shape
            for shape in page.all_shapes
            if (shape.cell_formula("BeginX") or "").startswith("_WALKGLUE(")
        )
        assert (
            dynamic.cell_formula("BeginX")
            == "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
        )
        assert dynamic.cell_value("ConFixedCode") == "0"
        dynamic_connections = [
            item.xml.attrib for item in page.connects if item.from_id == dynamic.ID
        ]
        assert {item["ToCell"] for item in dynamic_connections} == {"PinX"}
        assert {item["ToPart"] for item in dynamic_connections} == {"3"}

        diagonal_id = next(
            item.from_id
            for item in page.connects
            if item.xml.attrib["FromCell"] == "BeginX"
            and item.to_id == shape_b.ID
            and item.xml.attrib["ToCell"] == "Connections.bottom"
        )
        diagonal = next(shape for shape in page.all_shapes if shape.ID == diagonal_id)
        assert diagonal.cell_value("ConFixedCode") == "2"

        outer = _outer(page.find_shape_by_text("Outer"))
        inner = _outer(page.find_shape_by_text("Inner"))
        inner_label = page.find_shape_by_text("Inner")
        assert float(inner_label.cell_value("TxtHeight")) == pytest.approx(0.4)
        assert f"Sheet.{outer.ID}!SheetRef()" in inner.cell_formula("Relationships")
        assert f"Sheet.{inner.ID}!SheetRef()" in shape_a.cell_formula("Relationships")
        assert f"Sheet.{shape_a.ID}!SheetRef()" in inner.cell_formula("Relationships")
        assert f"Sheet.{shape_c.ID}!SheetRef()" in inner.cell_formula("Relationships")
        assert inner.cell_value("DontMoveChildren") == "1"
        resize = inner.xml.find(
            f"{namespace}Section[@N='User']/{namespace}Row[@N='msvSDContainerResize']/{namespace}Cell[@N='Value']"
        )
        assert resize.attrib["V"] == "0"

        callout = _outer(page.find_shape_by_text("101"))
        assert f"Sheet.{shape_a.ID}!SheetRef()" in callout.cell_formula("Relationships")
        assert float(callout.cell_value("TxtWidth")) == pytest.approx(0.8)
        assert callout.xml.find(
            f"{namespace}Section[@N='Geometry'][@IX='1']"
        ) is None
        leader_rows = callout.xml.findall(
            f"{namespace}Section[@N='Geometry'][@IX='0']/{namespace}Row"
        )
        assert [
            row.attrib["T"]
            for row in leader_rows
            if row.attrib.get("Del") != "1"
        ] == ["MoveTo", "LineTo"]
        leader_end = next(
            row for row in leader_rows if row.attrib.get("IX") == "2"
        )
        assert f"Sheet.{shape_a.ID}!PinX" in leader_end.find(
            f"{namespace}Cell[@N='X']"
        ).attrib["F"]


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


def test_render_ir_writes_projected_nonrectangular_ports_as_resize_formulas(
    tmp_path: Path,
) -> None:
    cases = (
        ("Hub", "__template_connector_hub__", "right", 0.25, "X", "Width*"),
        (
            "Database",
            "__template_database__",
            "right",
            0.5,
            "X",
            "MIN(Height/8,Width/8)",
        ),
        (
            "Terminator",
            "__template_terminator__",
            "left",
            0.1,
            "X",
            "MIN(Height/2,Width/4)",
        ),
        (
            "Data",
            "__template_input_output__",
            "right",
            0.25,
            "X",
            "MIN(Height/4,Width/4)",
        ),
        ("Delay", "__template_delay__", "right", 0.25, "X", "SQRT("),
        (
            "Rounded",
            "__template_controller__",
            "right",
            0.05,
            "X",
            "MIN(Width*0.1,Width/2,Height/2)",
        ),
        (
            "Document",
            "__template_document__",
            "bottom",
            0.5,
            "Y",
            "MIN(MIN(Width,Height)/8,Width/12)",
        ),
        (
            "Note",
            "__template_note__",
            "bottom",
            0.9,
            "Y",
            "User.XFoldLength",
        ),
    )
    planned = []
    expected: dict[str, tuple[float, float, str, str]] = {}
    for index, (label, marker, side, offset, formula_axis, fragment) in enumerate(cases):
        x = 0.5 + (index % 3) * 3.5
        y = 0.5 + (index // 3) * 2.0
        width = 2.0
        height = 1.0 if marker != "__template_connector_hub__" else 1.5
        x_fraction, y_fraction = port_fractions(
            marker, width, height, side, offset
        )
        port_name = f"port_{index}"
        planned.append(
            _shape(
                f"shape_projection_{index}",
                label,
                marker,
                (x, y, width, height),
                index,
            ).model_copy(
                update={
                    "ports": (
                        IRPort(
                            name=port_name,
                            side=side,
                            x=x + width * x_fraction,
                            y=y + height * (1 - y_fraction),
                        ),
                    )
                }
            )
        )
        expected[label] = (
            width * x_fraction,
            height * y_fraction,
            formula_axis,
            fragment,
        )
    ir = RendererIR(
        source_engine="v2",
        page=IRPage(
            width=11,
            height=7,
            orientation="landscape",
            margin=0.25,
            grid=0.25,
        ),
        regions=(),
        guides=(),
        shapes=tuple(planned),
        connectors=(),
        callouts=(),
    )

    output = render_ir(TEMPLATE, ir, tmp_path / "projected-port.vsdx")

    with VisioFile(str(output)) as document:
        page = document.get_page_by_name("Template Palette")
        for index, (label, *_unused) in enumerate(cases):
            rendered = _outer(
                next(shape for shape in page.all_shapes if shape.text.strip() == label)
            )
            row = rendered.xml.find(
                f"{namespace}Section[@N='Connection']/"
                f"{namespace}Row[@N='port_{index}']"
            )
            assert row is not None
            x_cell = row.find(f"{namespace}Cell[@N='X']")
            y_cell = row.find(f"{namespace}Cell[@N='Y']")
            assert x_cell is not None and y_cell is not None
            expected_x, expected_y, formula_axis, fragment = expected[label]
            assert float(x_cell.attrib["V"]) == pytest.approx(expected_x)
            assert float(y_cell.attrib["V"]) == pytest.approx(expected_y)
            formula_cell = x_cell if formula_axis == "X" else y_cell
            assert fragment in formula_cell.attrib["F"]


def test_professional_acceptance_candidate_is_structurally_valid(
    tmp_path: Path,
) -> None:
    output = render_ir(
        TEMPLATE,
        professional_acceptance_ir(),
        tmp_path / "g5-professional-acceptance.vsdx",
    )

    validate_vsdx_package(output)
    with VisioFile(str(output)) as document:
        page = document.get_page_by_name("Template Palette")
        housing = _outer(page.find_shape_by_text("Signal Processing System"))
        sensor = _outer(page.find_shape_by_text("Sensor"))
        controller = _outer(page.find_shape_by_text("Controller"))
        database = _outer(page.find_shape_by_text("Event Store"))
        assert (housing.x, housing.y, housing.width, housing.height) == pytest.approx(
            (5.5, 3.5, 10, 5.8)
        )
        assert housing.cells["Width"].xml.attrib["F"] == housing.cell_value("Width")
        assert sensor.cells["Width"].xml.attrib["F"] == sensor.cell_value("Width")
        for shape in (housing, sensor, controller, database):
            for name in ("PinX", "PinY", "Width", "Height", "LocPinX", "LocPinY"):
                assert shape.cells[name].xml.attrib["F"] == shape.cell_value(name)
        for shape in (sensor, controller, database):
            assert shape.xml.find(f"{namespace}Section[@N='Geometry']") is None
        assert database.xml.find(f"{namespace}Section[@N='Scratch']") is None
        assert controller.xml.find(f"{namespace}Section[@N='Control']") is None
        active_children = [
            child for child in housing.child_shapes if child.xml.attrib.get("Del") != "1"
        ]
        assert len(active_children) == 1
        header = active_children[0]
        hidden_roots = [child for child in housing.child_shapes if child.ID != header.ID]
        hidden = [
            descendant
            for root in [*hidden_roots, *header.child_shapes]
            for descendant in [root, *root.all_shapes]
        ]
        assert hidden and all(child.xml.attrib.get("Del") == "1" for child in hidden)
        assert all(child.cell_value("HideText") == "1" for child in hidden)
        assert all(child.cell_value("FillPattern") == "0" for child in hidden)
        assert all(child.cell_value("LinePattern") == "0" for child in hidden)
        assert all(
            geometries
            and all(
                geometry.find(f"{namespace}Cell[@N='NoShow']").attrib["V"] == "1"
                for geometry in geometries
            )
            for child in hidden
            for geometries in (
                child.xml.findall(f"{namespace}Section[@N='Geometry']"),
            )
        )
        header_geometry = header.xml.findall(f"{namespace}Section[@N='Geometry']")
        assert len(header_geometry) > 1
        active_geometry = next(
            section for section in header_geometry if section.attrib.get("IX") == "0"
        )
        assert {
            name: active_geometry.find(f"{namespace}Cell[@N='{name}']").attrib["V"]
            for name in ("NoShow", "NoFill", "NoLine")
        } == {"NoShow": "0", "NoFill": "0", "NoLine": "0"}
        assert all(
            section.find(f"{namespace}Cell[@N='NoShow']").attrib["V"] == "1"
            for section in header_geometry
            if section.attrib.get("IX") != "0"
        )
        assert any(
            row.attrib.get("Del") == "1"
            for row in active_geometry.findall(f"{namespace}Row")
        )
        assert header.cell_value("FillForegnd") == "#234567"
        assert header.cell_value("FillPattern") == "1"
        header_color = header.xml.find(
            f"{namespace}Section[@N='Character']/{namespace}Row[@IX='0']/"
            f"{namespace}Cell[@N='Color']"
        )
        assert header_color is not None and header_color.attrib["V"] == "#FFFFFF"
        housing_rows = housing.xml.findall(
            f"{namespace}Section[@N='Geometry'][@IX='0']/{namespace}Row"
        )
        assert [row.attrib["T"] for row in housing_rows] == [
            "MoveTo",
            "LineTo",
            "LineTo",
            "LineTo",
            "LineTo",
        ]
        assert f"Sheet.{sensor.ID}!SheetRef()" in housing.cell_formula("Relationships")
        assert f"Sheet.{controller.ID}!SheetRef()" in housing.cell_formula(
            "Relationships"
        )
        assert f"Sheet.{database.ID}!SheetRef()" in housing.cell_formula(
            "Relationships"
        )
        assert len({item.from_id for item in page.connects}) == 2
        connector_ids = {item.from_id for item in page.connects}
        for connector_id in connector_ids:
            connector = next(
                shape for shape in page.all_shapes if shape.ID == connector_id
            )
            assert connector.cell_formula("BeginX").startswith("_WALKGLUE(")
            assert connector.cell_formula("EndX").startswith("_WALKGLUE(")
