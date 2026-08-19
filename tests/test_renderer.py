from collections import Counter
from pathlib import Path
import re
import shutil
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from vsdx import VisioFile, namespace

import visiogen.renderer as renderer


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

        connected_ids = {
            connection.to_id
            for connection in page.connects
            if connection.from_id == connector.ID
        }
        assert connected_ids == {process.ID, component.ID}
        assert f"Sheet.{process.ID}!" in connector.cell_formula("BeginX")
        assert f"Sheet.{component.ID}!" in connector.cell_formula("EndX")


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


def test_render_feasibility_spike_refuses_to_overwrite_template(
    tmp_path: Path,
) -> None:
    template_copy = tmp_path / "template.vsdx"
    shutil.copyfile(TEMPLATE_PATH, template_copy)

    with pytest.raises(ValueError, match="overwrite the canonical template"):
        renderer.render_feasibility_spike(template_copy, template_copy)
