import hashlib
import io
import os
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
import re
import shutil
import threading
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from vsdx import Shape, VisioFile, namespace

import visiogen.renderer as renderer
from visiogen.layout import LayoutResult, PageGeometry
from visiogen.models import DiagramEdge, DiagramGraph, DiagramNode, NodeType


TEMPLATE_PATH = Path(__file__).parents[1] / "templates" / "template.vsdx"
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
        "__template_connector__",
    }
)


def _outer_shape(shape: Shape) -> Shape:
    current = shape
    while isinstance(current.parent, Shape) and current.parent.ID is not None:
        current = current.parent
    return current


def _node(
    node_id: str,
    node_type: NodeType,
    label: str,
    geometry: tuple[float, float, float, float],
    *,
    parent_id: str | None = None,
    reference_number: str | None = None,
) -> DiagramNode:
    x, y, width, height = geometry
    return DiagramNode(
        id=node_id,
        type=node_type,
        label=label,
        parent_id=parent_id,
        reference_number=reference_number,
        x=x,
        y=y,
        width=width,
        height=height,
    )


def test_canonical_template_contains_complete_production_vocabulary() -> None:
    with VisioFile(str(TEMPLATE_PATH)) as document:
        page = document.get_page_by_name("Template Palette")
        counts = Counter(shape.text.strip() for shape in page.all_shapes)
        shape_ids = [shape.ID for shape in page.all_shapes]

        assert page.width == pytest.approx(22.0)
        assert page.height == pytest.approx(17.0)
        assert len(page.child_shapes) == 20
        assert len(shape_ids) == len(set(shape_ids))

    assert {
        marker: counts[marker] for marker in PRODUCTION_TEMPLATE_MARKERS
    } == dict.fromkeys(PRODUCTION_TEMPLATE_MARKERS, 1)


def test_load_template_palette_finds_each_marker_once() -> None:
    with renderer.load_template_palette(TEMPLATE_PATH) as palette:
        assert palette.page.name == "Template Palette"
        assert set(palette.shapes) == set(renderer.TEMPLATE_MARKERS)
        assert all(
            palette.shapes[marker].text == marker for marker in renderer.TEMPLATE_MARKERS
        )


def test_render_layout_copies_containers_before_children_with_exact_geometry(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "nodes.vsdx"
    source_hash = hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Contained system",
            diagram_type="system_block",
            orientation="left_to_right",
            nodes=[
                _node("child", "controller", "Controller", (3.0, 3.0, 2.5, 1.0), parent_id="box"),
                _node("box", "subsystem", "Control subsystem", (4.0, 3.0, 7.0, 4.5)),
            ],
        ),
        page=PageGeometry(width=9.0, height=6.0),
    )

    renderer.render_layout(TEMPLATE_PATH, layout, output_path)

    assert hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest() == source_hash
    with VisioFile(str(output_path)) as document:
        page = document.get_page_by_name("Template Palette")
        container = _outer_shape(page.find_shape_by_text("Control subsystem"))
        child = _outer_shape(page.find_shape_by_text("Controller"))
        top_level_ids = [shape.ID for shape in page.child_shapes]
        assert top_level_ids.index(container.ID) < top_level_ids.index(child.ID)
        assert (container.x, container.y, container.width, container.height) == pytest.approx(
            (4.0, 3.0, 7.0, 4.5)
        )
        assert (child.x, child.y, child.width, child.height) == pytest.approx(
            (3.0, 3.0, 2.5, 1.0)
        )
        assert page.width == pytest.approx(9.0)
        assert page.height == pytest.approx(6.0)
        remaining_markers = {
            shape.text.strip()
            for shape in page.all_shapes
            if shape.text.strip() in PRODUCTION_TEMPLATE_MARKERS
        }
        assert remaining_markers == set()


def test_render_layout_preserves_explicit_reference_number_as_targeted_callout(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "reference.vsdx"
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Referenced component",
            diagram_type="component_schematic",
            orientation="left_to_right",
            nodes=[
                _node(
                    "controller",
                    "controller",
                    "Controller",
                    (3.0, 3.0, 2.5, 1.0),
                    reference_number="007",
                )
            ],
        ),
        page=PageGeometry(width=7.0, height=6.0),
    )

    renderer.render_layout(TEMPLATE_PATH, layout, output_path)

    with VisioFile(str(output_path)) as document:
        page = document.get_page_by_name("Template Palette")
        controller = _outer_shape(page.find_shape_by_text("Controller"))
        callouts = [shape for shape in page.all_shapes if shape.text.strip() == "007"]
        assert len(callouts) == 1
        callout = _outer_shape(callouts[0])
        assert f"Sheet.{controller.ID}!" in callout.cell_formula("Relationships")
        target_row = callout.xml.find(
            f"{namespace}Section[@N='User']/{namespace}Row[@N='msvSDTargetIntersection']"
        )
        target_formula = target_row.find(f"{namespace}Cell[@N='Value']").attrib["F"]
        assert f"Sheet.{controller.ID}!" in target_formula
        leader_row = callout.xml.find(
            f"{namespace}Section[@N='User']/{namespace}Row[@N='LeaderEnd']"
        )
        leader_formula = leader_row.find(f"{namespace}Cell[@N='Value']").attrib["F"]
        assert leader_formula == "User.msvSDTargetIntersection"
        geometry = callout.xml.find(f"{namespace}Section[@N='Geometry'][@IX='0']")
        leader_endpoint = geometry.find(f"{namespace}Row[@T='LineTo'][@IX='2']")
        assert leader_endpoint.find(f"{namespace}Cell[@N='X']").attrib["F"] == "User.LeaderEnd"
        assert leader_endpoint.find(f"{namespace}Cell[@N='Y']").attrib["F"] == "User.LeaderEnd"
        assert callout.x > controller.x


def test_reference_callout_stays_inside_layout_page(tmp_path: Path) -> None:
    output_path = tmp_path / "bounded-reference.vsdx"
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Bounded reference",
            diagram_type="component_schematic",
            orientation="left_to_right",
            nodes=[
                _node(
                    "sensor",
                    "sensor",
                    "Edge sensor",
                    (6.0, 2.0, 1.5, 1.5),
                    reference_number="120",
                )
            ],
        ),
        page=PageGeometry(width=7.0, height=4.0),
    )

    renderer.render_layout(TEMPLATE_PATH, layout, output_path)

    with VisioFile(str(output_path)) as document:
        page = document.get_page_by_name("Template Palette")
        callout = _outer_shape(page.find_shape_by_text("120"))
        assert callout.x - callout.width / 2 >= 0
        assert callout.x + callout.width / 2 <= page.width
        assert callout.y - callout.height / 2 >= 0
        assert callout.y + callout.height / 2 <= page.height


def test_render_layout_rejects_page_too_small_for_reference_callout(
    tmp_path: Path,
) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Impossible callout page",
            diagram_type="component_schematic",
            orientation="left_to_right",
            nodes=[
                _node(
                    "component",
                    "component",
                    "Part",
                    (0.1, 0.1, 0.1, 0.1),
                    reference_number="10",
                )
            ],
        ),
        page=PageGeometry(width=0.2, height=0.2),
    )

    with pytest.raises(
        renderer.RenderingError,
        match="reference callout for node 'component' cannot fit inside the layout page",
    ):
        renderer.render_layout(TEMPLATE_PATH, layout, tmp_path / "too-small.vsdx")


def test_render_layout_auto_numbers_around_explicit_references(tmp_path: Path) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Mixed references",
            diagram_type="component_schematic",
            orientation="left_to_right",
            nodes=[
                _node("automatic", "component", "Automatic", (2.0, 2.0, 2.0, 1.0)),
                _node(
                    "explicit",
                    "component",
                    "Explicit",
                    (6.0, 2.0, 2.0, 1.0),
                    reference_number="1",
                ),
            ],
        ),
        page=PageGeometry(width=9.0, height=5.0),
    )
    output = tmp_path / "mixed-references.vsdx"

    renderer.render_layout(
        TEMPLATE_PATH,
        layout,
        output,
        automatic_reference_numbers=True,
    )

    with VisioFile(str(output)) as document:
        page = document.get_page_by_name("Template Palette")
        labels = Counter(shape.text.strip() for shape in page.all_shapes)
        assert labels["1"] == 1
        assert labels["2"] == 1


def test_render_layout_auto_numbers_only_when_explicitly_enabled(tmp_path: Path) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Optional references",
            diagram_type="system_block",
            orientation="left_to_right",
            nodes=[
                _node("sensor", "sensor", "Sensor", (2.0, 2.0, 1.5, 1.5)),
                _node("controller", "controller", "Controller", (5.0, 2.0, 2.5, 1.0)),
            ],
        ),
        page=PageGeometry(width=8.0, height=5.0),
    )
    default_output = tmp_path / "references-off.vsdx"
    enabled_output = tmp_path / "references-on.vsdx"

    renderer.render_layout(TEMPLATE_PATH, layout, default_output)
    renderer.render_layout(
        TEMPLATE_PATH,
        layout,
        enabled_output,
        automatic_reference_numbers=True,
    )

    with VisioFile(str(default_output)) as document:
        page = document.get_page_by_name("Template Palette")
        assert page.find_shape_by_text("1") is None
        assert page.find_shape_by_text("2") is None
    with VisioFile(str(enabled_output)) as document:
        page = document.get_page_by_name("Template Palette")
        assert page.find_shape_by_text("1") is not None
        assert page.find_shape_by_text("2") is not None


def test_render_layout_creates_styled_labeled_glued_connector(tmp_path: Path) -> None:
    output_path = tmp_path / "connector.vsdx"
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Connected system",
            diagram_type="system_block",
            orientation="left_to_right",
            nodes=[
                _node("sensor", "sensor", "Sensor", (2.0, 2.5, 1.5, 1.5)),
                _node("controller", "controller", "Controller", (6.0, 2.5, 2.5, 1.0)),
            ],
            edges=[
                DiagramEdge(
                    id="data-link",
                    source="sensor",
                    target="controller",
                    relation="data",
                    direction="bidirectional",
                    label="synchronizes",
                    style="dotted",
                )
            ],
        ),
        page=PageGeometry(width=9.0, height=5.0),
    )

    renderer.render_layout(TEMPLATE_PATH, layout, output_path)

    with VisioFile(str(output_path)) as document:
        page = document.get_page_by_name("Template Palette")
        sensor = _outer_shape(page.find_shape_by_text("Sensor"))
        controller = _outer_shape(page.find_shape_by_text("Controller"))
        connector = _outer_shape(page.find_shape_by_text("synchronizes"))
        connected_ids = {
            connection.to_id
            for connection in page.connects
            if connection.from_id == connector.ID
        }
        assert connected_ids == {sensor.ID, controller.ID}
        connector_rows = {
            connection.xml.attrib["FromCell"]: connection.xml.attrib
            for connection in page.connects
            if connection.from_id == connector.ID
        }
        assert connector_rows["BeginX"]["ToSheet"] == sensor.ID
        assert connector_rows["BeginX"]["ToCell"] == "PinX"
        assert connector_rows["BeginX"]["ToPart"] == "3"
        assert connector_rows["EndX"]["ToSheet"] == controller.ID
        assert connector_rows["EndX"]["ToCell"] == "PinX"
        assert connector_rows["EndX"]["ToPart"] == "3"
        assert connector.cell_formula("BeginX") == (
            "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
        )
        assert connector.cell_formula("BeginY") == (
            "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
        )
        assert connector.cell_formula("EndX") == (
            "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"
        )
        assert connector.cell_formula("EndY") == (
            "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"
        )
        assert connector.cell_formula("BegTrigger") == (
            f"_XFTRIGGER(Sheet.{sensor.ID}!EventXFMod)"
        )
        assert connector.cell_formula("EndTrigger") == (
            f"_XFTRIGGER(Sheet.{controller.ID}!EventXFMod)"
        )
        assert connector.cell_value("ConFixedCode") == "0"
        assert float(connector.cell_value("BeginX")) == pytest.approx(2.75)
        assert float(connector.cell_value("BeginY")) == pytest.approx(2.5)
        assert float(connector.cell_value("EndX")) == pytest.approx(4.75)
        assert float(connector.cell_value("EndY")) == pytest.approx(2.5)
        assert float(connector.cell_value("PinX")) == pytest.approx(3.75)
        assert float(connector.cell_value("PinY")) == pytest.approx(2.5)
        assert float(connector.cell_value("Width")) == pytest.approx(2.0)
        assert float(connector.cell_value("Height")) == pytest.approx(0.25)
        assert float(connector.cell_value("LocPinX")) == pytest.approx(1.0)
        assert float(connector.cell_value("LocPinY")) == pytest.approx(0.125)
        assert connector.cell_formula("PinX") == "GUARD((BeginX+EndX)/2)"
        assert connector.cell_formula("PinY") == "GUARD(BeginY)"
        assert connector.cell_formula("Width") == "GUARD(EndX-BeginX)"
        assert connector.cell_formula("Height") == "GUARD(0.25DL)"
        assert connector.cell_formula("LocPinX") == "GUARD(Width/2)"
        assert connector.cell_formula("LocPinY") == "GUARD(Height/2)"
        assert connector.cell_value("BeginArrow") == "4"
        assert connector.cell_value("EndArrow") == "4"
        assert connector.cell_value("LinePattern") == "3"
        assert float(connector.cell_value("LineWeight")) == pytest.approx(1.0 / 72.0)
        assert connector.cell_value("LineColor") == "#000000"


def test_render_layout_keeps_self_connector_cache_outside_node(tmp_path: Path) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Self transition",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[_node("step", "process", "Step", (3.0, 2.0, 2.0, 1.0))],
            edges=[DiagramEdge(source="step", target="step", relation="flow")],
        ),
        page=PageGeometry(width=6.0, height=4.0),
    )
    output = tmp_path / "self-connector.vsdx"

    renderer.render_layout(TEMPLATE_PATH, layout, output)

    with VisioFile(str(output)) as document:
        page = document.get_page_by_name("Template Palette")
        connector_id = page.connects[0].from_id
        connector = next(shape for shape in page.all_shapes if shape.ID == connector_id)
        assert float(connector.cell_value("BeginX")) == pytest.approx(4.0)
        assert float(connector.cell_value("BeginY")) == pytest.approx(1.75)
        assert float(connector.cell_value("EndX")) == pytest.approx(4.0)
        assert float(connector.cell_value("EndY")) == pytest.approx(2.25)
        assert {row.to_id for row in page.connects} == {
            _outer_shape(page.find_shape_by_text("Step")).ID
        }
        assert all(
            row.xml.attrib["ToCell"] == "PinX"
            and row.xml.attrib["ToPart"] == "3"
            for row in page.connects
        )


def test_render_layout_uses_relation_style_when_edge_style_is_omitted(
    tmp_path: Path,
) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Default association style",
            diagram_type="system_block",
            orientation="left_to_right",
            nodes=[
                _node("source", "process", "Source", (2.0, 2.0, 2.0, 1.0)),
                _node("target", "component", "Target", (6.0, 2.0, 2.0, 1.0)),
            ],
            edges=[
                DiagramEdge(
                    id="association",
                    source="source",
                    target="target",
                    relation="association",
                    direction="none",
                )
            ],
        ),
        page=PageGeometry(width=8.0, height=4.0),
    )
    output = tmp_path / "default-association.vsdx"

    renderer.render_layout(TEMPLATE_PATH, layout, output)

    with VisioFile(str(output)) as document:
        page = document.get_page_by_name("Template Palette")
        connector_id = page.connects[0].from_id
        connector = next(shape for shape in page.all_shapes if shape.ID == connector_id)
        assert connector.cell_value("LinePattern") == "3"
        assert connector.cell_value("BeginArrow") == "0"
        assert connector.cell_value("EndArrow") == "0"


def test_render_layout_rejects_edge_with_missing_endpoint(tmp_path: Path) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Broken connection",
            diagram_type="system_block",
            orientation="left_to_right",
            nodes=[_node("sensor", "sensor", "Sensor", (2.0, 2.0, 1.5, 1.5))],
            edges=[DiagramEdge(source="sensor", target="missing", relation="data")],
        ),
        page=PageGeometry(width=6.0, height=4.0),
    )

    with pytest.raises(
        renderer.RenderingError,
        match="edge references missing rendered endpoint 'missing'",
    ):
        renderer.render_layout(TEMPLATE_PATH, layout, tmp_path / "broken.vsdx")


@pytest.mark.parametrize(
    "geometry",
    [
        (float("nan"), 2.0, 2.625, 0.75),
        (2.0, float("inf"), 2.625, 0.75),
        (2.0, 2.0, -1.0, 0.75),
        (2.0, 2.0, 2.625, 0.0),
    ],
)
def test_render_layout_rejects_nonfinite_or_nonpositive_geometry(
    geometry: tuple[float, float, float, float],
    tmp_path: Path,
) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Invalid geometry",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[_node("step", "process", "Step", geometry)],
        ),
        page=PageGeometry(width=5.0, height=4.0),
    )

    with pytest.raises(
        renderer.RenderingError,
        match="finite coordinates and positive dimensions required for node 'step'",
    ):
        renderer.render_layout(TEMPLATE_PATH, layout, tmp_path / "invalid-geometry.vsdx")


@pytest.mark.parametrize(
    "geometry",
    [
        (-1.0, 2.0, 1.0, 1.0),
        (4.8, 2.0, 1.0, 1.0),
        (2.0, 0.2, 1.0, 1.0),
        (2.0, 3.8, 1.0, 1.0),
    ],
)
def test_render_layout_rejects_node_outside_page(
    geometry: tuple[float, float, float, float],
    tmp_path: Path,
) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Out of bounds",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[_node("step", "process", "Step", geometry)],
        ),
        page=PageGeometry(width=5.0, height=4.0),
    )

    with pytest.raises(
        renderer.RenderingError,
        match="node 'step' lies outside the layout page",
    ):
        renderer.render_layout(TEMPLATE_PATH, layout, tmp_path / "outside.vsdx")


def test_render_layout_rejects_nonfinite_page_geometry(tmp_path: Path) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Invalid page",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[_node("step", "process", "Step", (2.0, 2.0, 2.625, 0.75))],
        ),
        page=PageGeometry(width=float("inf"), height=4.0),
    )

    with pytest.raises(renderer.RenderingError, match="finite page geometry required"):
        renderer.render_layout(TEMPLATE_PATH, layout, tmp_path / "invalid-page.vsdx")


def test_namespace_serializer_remaps_unknown_prefix_without_global_state() -> None:
    root_namespace = "urn:visiogen:root"
    foreign_namespace = "urn:visiogen:foreign"
    root = ET.Element(f"{{{root_namespace}}}root")
    ET.SubElement(root, f"{{{foreign_namespace}}}child")
    contents: dict[str, io.BytesIO] = {}

    renderer._namespace_safe_xml_to_file(
        ET.ElementTree(root),
        "part.xml",
        contents,
    )

    serialized = contents["part.xml"].getvalue()
    assert b"ns0:" not in serialized
    assert b"ns1:" not in serialized
    parsed = ET.fromstring(serialized)
    assert parsed.tag == f"{{{root_namespace}}}root"
    assert list(parsed)[0].tag == f"{{{foreign_namespace}}}child"


def test_namespace_serializer_rejects_empty_tree() -> None:
    with pytest.raises(renderer.RenderingError, match="empty XML tree"):
        renderer._namespace_safe_xml_to_file(ET.ElementTree(), "empty.xml", {})


def test_render_layout_restores_elementtree_namespace_registry(tmp_path: Path) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Namespace isolation",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[_node("step", "process", "Step", (2.0, 2.0, 2.625, 0.75))],
        ),
        page=PageGeometry(width=5.0, height=4.0),
    )
    namespace_map = dict(getattr(ET, "_namespace_map"))

    renderer.render_layout(TEMPLATE_PATH, layout, tmp_path / "namespace-safe.vsdx")

    assert getattr(ET, "_namespace_map") == namespace_map


def test_render_layout_does_not_disturb_concurrent_elementtree_serialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Concurrent namespace isolation",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[_node("step", "process", "Step", (2.0, 2.0, 2.625, 0.75))],
        ),
        page=PageGeometry(width=5.0, height=4.0),
    )
    unrelated_namespace = "urn:visiogen:unrelated"
    namespace_registry = getattr(ET, "_namespace_map")
    original_namespaces = dict(namespace_registry)
    ET.register_namespace("", unrelated_namespace)
    serializer_entered = threading.Event()
    release_serializer = threading.Event()
    render_errors: list[BaseException] = []
    original_serializer = renderer._namespace_safe_xml_to_file

    def blocking_serializer(*args: Any, **kwargs: Any) -> None:
        original_serializer(*args, **kwargs)
        serializer_entered.set()
        assert release_serializer.wait(timeout=10)

    monkeypatch.setattr(renderer, "_namespace_safe_xml_to_file", blocking_serializer)

    def run_renderer() -> None:
        try:
            renderer.render_layout(
                TEMPLATE_PATH,
                layout,
                tmp_path / "concurrent-namespace.vsdx",
            )
        except BaseException as error:  # pragma: no cover - assertion reports detail
            render_errors.append(error)

    worker = threading.Thread(target=run_renderer)
    worker.start()
    try:
        assert serializer_entered.wait(timeout=10)
        unrelated_xml = ET.tostring(
            ET.Element(f"{{{unrelated_namespace}}}root"),
            encoding="unicode",
        )
    finally:
        release_serializer.set()
        worker.join(timeout=10)
        namespace_registry.clear()
        namespace_registry.update(original_namespaces)

    assert not worker.is_alive()
    assert not render_errors
    assert unrelated_xml.startswith(f'<root xmlns="{unrelated_namespace}"')


def test_render_layout_does_not_print_library_debug_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Quiet rendering",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[
                _node("step", "process", "Step", (2.0, 2.0, 2.625, 0.75)),
                _node("target", "component", "Target", (4.5, 2.0, 1.0, 1.0)),
            ],
            edges=[
                DiagramEdge(
                    id="quiet-edge",
                    source="step",
                    target="target",
                    relation="flow",
                    direction="forward",
                )
            ],
        ),
        page=PageGeometry(width=5.0, height=4.0),
    )

    renderer.render_layout(TEMPLATE_PATH, layout, tmp_path / "quiet.vsdx")

    assert capsys.readouterr().out == ""


def test_render_layout_requires_complete_node_geometry(tmp_path: Path) -> None:
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Missing geometry",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[DiagramNode(id="start", type="terminator", label="Start")],
        ),
        page=PageGeometry(width=8.0, height=6.0),
    )

    with pytest.raises(renderer.RenderingError, match="geometry required for node 'start'"):
        renderer.render_layout(TEMPLATE_PATH, layout, tmp_path / "invalid.vsdx")


def test_render_feasibility_spike_copies_relabels_and_repositions_parts(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "minimal.vsdx"

    renderer.render_feasibility_spike(TEMPLATE_PATH, output_path)

    assert output_path.is_file()
    with VisioFile(str(output_path)) as document:
        page = document.get_page_by_name("Template Palette")
        assert page is not None

        generated = {
            label: [shape for shape in page.all_shapes if shape.text.strip() == label]
            for label in renderer.GENERATED_LABELS.values()
        }
        assert all(len(matches) == 1 for matches in generated.values())

        process = generated["Generated Process"][0]
        component = generated["Generated Component"][0]
        assert process.x == pytest.approx(2.5)
        assert process.y == pytest.approx(5.0)
        assert component.x == pytest.approx(7.5)
        assert component.y == pytest.approx(5.0)


def test_rendered_output_excludes_template_palette_objects(tmp_path: Path) -> None:
    output_path = tmp_path / "minimal.vsdx"
    renderer.render_feasibility_spike(TEMPLATE_PATH, output_path)

    with VisioFile(str(output_path)) as document:
        page = document.get_page_by_name("Template Palette")
        remaining_markers = {
            shape.text.strip()
            for shape in page.all_shapes
            if shape.text.strip() in renderer.TEMPLATE_MARKERS
        }

    assert remaining_markers == set()


def test_generated_connector_is_glued_to_generated_endpoints(tmp_path: Path) -> None:
    output_path = tmp_path / "minimal.vsdx"
    renderer.render_feasibility_spike(TEMPLATE_PATH, output_path)

    with VisioFile(str(output_path)) as document:
        page = document.get_page_by_name("Template Palette")
        process = page.find_shape_by_text("Generated Process")
        component = page.find_shape_by_text("Generated Component")
        connector = page.find_shape_by_text("feeds")

        connected_rows = {
            connection.xml.attrib["FromCell"]: connection
            for connection in page.connects
            if connection.from_id == connector.ID
        }
        assert {row.to_id for row in connected_rows.values()} == {
            process.ID,
            component.ID,
        }
        assert all(
            row.xml.attrib["ToCell"] == "PinX"
            and row.xml.attrib["ToPart"] == "3"
            for row in connected_rows.values()
        )
        assert connector.cell_formula("BeginX") == (
            "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
        )
        assert connector.cell_formula("EndX") == (
            "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"
        )
        assert f"Sheet.{process.ID}!" in connector.cell_formula("BegTrigger")
        assert f"Sheet.{component.ID}!" in connector.cell_formula("EndTrigger")
        assert float(connector.cell_value("BeginX")) == pytest.approx(
            process.x + process.width / 2
        )
        assert float(connector.cell_value("EndX")) == pytest.approx(
            component.x - component.width / 2
        )


def test_generated_callout_targets_generated_component(tmp_path: Path) -> None:
    output_path = tmp_path / "minimal.vsdx"
    renderer.render_feasibility_spike(TEMPLATE_PATH, output_path)

    with VisioFile(str(output_path)) as document:
        page = document.get_page_by_name("Template Palette")
        component = page.find_shape_by_text("Generated Component")
        callout = page.find_shape_by_text("101")

        assert f"Sheet.{component.ID}!" in callout.cell_formula("Relationships")


def test_generated_callout_leader_touches_generated_component(tmp_path: Path) -> None:
    output_path = tmp_path / "minimal.vsdx"
    renderer.render_feasibility_spike(TEMPLATE_PATH, output_path)

    with VisioFile(str(output_path)) as document:
        page = document.get_page_by_name("Template Palette")
        component = page.find_shape_by_text("Generated Component")
        callout = page.find_shape_by_text("101")
        geometry = callout.xml.find(f"{namespace}Section[@N='Geometry'][@IX='0']")
        leader_end = geometry.find(f"{namespace}Row[@T='LineTo'][@IX='2']")
        local_x = float(leader_end.find(f"{namespace}Cell[@N='X']").attrib["V"])
        local_y = float(leader_end.find(f"{namespace}Cell[@N='Y']").attrib["V"])
        global_x = callout.x - float(callout.cell_value("LocPinX")) + local_x
        global_y = callout.y - float(callout.cell_value("LocPinY")) + local_y
        target_row = callout.xml.find(
            f"{namespace}Section[@N='User']/{namespace}Row[@N='msvSDTargetIntersection']"
        )
        target_cell = target_row.find(f"{namespace}Cell[@N='Value']")
        target_value = target_cell.attrib["V"]
        target_formula = target_cell.attrib["F"]
        match = re.fullmatch(r"PNT\(([^,]+),([^\)]+)\)", target_value)

        assert match is not None
        assert float(match.group(1)) == pytest.approx(local_x)
        assert float(match.group(2)) == pytest.approx(local_y)
        assert f"Sheet.{component.ID}!PinX" in target_formula
        assert f"Sheet.{component.ID}!PinY" in target_formula
        assert f"Sheet.{component.ID}!Height" in target_formula
        assert component.x - component.width / 2 <= global_x <= component.x + component.width / 2
        assert global_y == pytest.approx(component.y - component.height / 2)


def test_render_feasibility_spike_does_not_print_library_debug_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    renderer.render_feasibility_spike(TEMPLATE_PATH, tmp_path / "minimal.vsdx")

    assert capsys.readouterr().out == ""


def test_generated_vsdx_has_unique_shape_ids(tmp_path: Path) -> None:
    output_path = tmp_path / "minimal.vsdx"
    renderer.render_feasibility_spike(TEMPLATE_PATH, output_path)

    with ZipFile(output_path) as package:
        page_xml = ET.fromstring(package.read("visio/pages/page1.xml"))
    shape_ids = [
        element.attrib["ID"]
        for element in page_xml.iter(f"{namespace}Shape")
        if "ID" in element.attrib
    ]
    duplicates = {
        shape_id: count
        for shape_id, count in Counter(shape_ids).items()
        if count > 1
    }

    assert duplicates == {}


def test_generated_vsdx_uses_declared_namespaces_without_ns_prefixes(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "minimal.vsdx"
    renderer.render_feasibility_spike(TEMPLATE_PATH, output_path)

    with ZipFile(output_path) as package:
        prefixed_parts = [
            name
            for name in package.namelist()
            if name.endswith((".xml", ".rels"))
            and re.search(rb"</?ns\d+:", package.read(name))
        ]

    assert prefixed_parts == []


def test_render_layout_preserves_destination_after_serialization_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "existing.vsdx"
    destination.write_bytes(b"ORIGINAL")
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Atomic failure",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[_node("step", "process", "Step", (2.0, 2.0, 2.625, 0.75))],
        ),
        page=PageGeometry(width=5.0, height=4.0),
    )

    def fail_serialization(document: VisioFile) -> None:
        raise RuntimeError("injected serialization failure")

    monkeypatch.setattr(renderer, "_write_document_parts", fail_serialization)

    with pytest.raises(RuntimeError, match="injected serialization failure"):
        renderer.render_layout(TEMPLATE_PATH, layout, destination)

    assert destination.read_bytes() == b"ORIGINAL"
    assert not list(tmp_path.glob(f".{destination.name}.*.vsdx"))


def test_render_layout_atomically_replaces_raced_template_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_copy = tmp_path / "template.vsdx"
    output_alias = tmp_path / "output.vsdx"
    shutil.copyfile(TEMPLATE_PATH, template_copy)
    source_hash = hashlib.sha256(template_copy.read_bytes()).hexdigest()
    original_loader = renderer.load_template_palette

    @contextmanager
    def racing_loader(*args: Any, **kwargs: Any):
        with original_loader(*args, **kwargs) as palette:
            output_alias.unlink(missing_ok=True)
            os.link(template_copy, output_alias)
            yield palette

    monkeypatch.setattr(renderer, "load_template_palette", racing_loader)
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Raced destination",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[_node("step", "process", "Step", (2.0, 2.0, 2.625, 0.75))],
        ),
        page=PageGeometry(width=5.0, height=4.0),
    )

    renderer.render_layout(template_copy, layout, output_alias)

    assert hashlib.sha256(template_copy.read_bytes()).hexdigest() == source_hash
    assert not template_copy.samefile(output_alias)


def test_render_layout_refuses_hard_link_alias_of_template(tmp_path: Path) -> None:
    template_copy = tmp_path / "template.vsdx"
    output_alias = tmp_path / "output.vsdx"
    shutil.copyfile(TEMPLATE_PATH, template_copy)
    os.link(template_copy, output_alias)
    source_hash = hashlib.sha256(template_copy.read_bytes()).hexdigest()
    layout = LayoutResult(
        graph=DiagramGraph(
            title="Protected template",
            diagram_type="flowchart",
            orientation="top_to_bottom",
            nodes=[_node("step", "process", "Step", (2.0, 2.0, 2.625, 0.75))],
        ),
        page=PageGeometry(width=5.0, height=4.0),
    )

    with pytest.raises(ValueError, match="overwrite the canonical template"):
        renderer.render_layout(template_copy, layout, output_alias)

    assert hashlib.sha256(template_copy.read_bytes()).hexdigest() == source_hash


def test_render_feasibility_spike_refuses_to_overwrite_template(
    tmp_path: Path,
) -> None:
    template_copy = tmp_path / "template.vsdx"
    shutil.copyfile(TEMPLATE_PATH, template_copy)

    with pytest.raises(ValueError, match="overwrite the canonical template"):
        renderer.render_feasibility_spike(template_copy, template_copy)
