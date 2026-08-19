import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from vsdx import VisioFile, namespace

from visiogen.layouts.graphviz_layout import GraphvizLayout
from visiogen.models import DiagramGraph
from visiogen.renderer import render_layout
from visiogen.shape_mapper import PRODUCTION_TEMPLATE_MARKERS


PROJECT_ROOT = Path(__file__).parents[1]
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "template.vsdx"
FIXTURE_PATHS = (
    PROJECT_ROOT / "tests" / "fixtures" / "graphs" / "expected" / "linear_flow.json",
    PROJECT_ROOT / "tests" / "fixtures" / "graphs" / "expected" / "basic_system.json",
    PROJECT_ROOT / "tests" / "fixtures" / "graphs" / "renderer" / "headphone.json",
)


@pytest.mark.parametrize("fixture_path", FIXTURE_PATHS, ids=lambda path: path.stem)
def test_renderer_fixture_produces_structurally_valid_editable_package(
    fixture_path: Path,
    tmp_path: Path,
) -> None:
    graph = DiagramGraph.model_validate(json.loads(fixture_path.read_text()))
    layout = GraphvizLayout().layout(graph)
    output_path = tmp_path / f"{fixture_path.stem}.vsdx"
    source_hash = hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()

    render_layout(TEMPLATE_PATH, layout, output_path)

    assert hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest() == source_hash
    with ZipFile(output_path) as package:
        xml_parts = [
            name for name in package.namelist() if name.endswith((".xml", ".rels"))
        ]
        for part_name in xml_parts:
            ET.fromstring(package.read(part_name))
        page_xml = ET.fromstring(package.read("visio/pages/page1.xml"))
        shape_ids = [
            element.attrib["ID"]
            for element in page_xml.iter(f"{namespace}Shape")
            if "ID" in element.attrib
        ]
        assert len(shape_ids) == len(set(shape_ids))

    with VisioFile(str(output_path)) as document:
        page = document.get_page_by_name("Template Palette")
        labels = Counter(shape.text.strip() for shape in page.all_shapes)
        expected_labels = [node.label for node in layout.graph.nodes]
        expected_labels.extend(
            node.reference_number
            for node in layout.graph.nodes
            if node.reference_number is not None
        )
        expected_labels.extend(
            edge.label for edge in layout.graph.edges if edge.label is not None
        )
        assert {label: labels[label] for label in expected_labels} == dict.fromkeys(
            expected_labels, 1
        )
        assert not set(labels) & PRODUCTION_TEMPLATE_MARKERS
        expected_top_level = (
            len(layout.graph.nodes)
            + len(layout.graph.edges)
            + sum(node.reference_number is not None for node in layout.graph.nodes)
        )
        assert len(page.child_shapes) == expected_top_level
        connector_ids = {connect.from_id for connect in page.connects}
        assert len(connector_ids) == len(layout.graph.edges)
        shapes_by_id = {shape.ID: shape for shape in page.all_shapes}
        for connector_id in connector_ids:
            connections = [
                connect for connect in page.connects if connect.from_id == connector_id
            ]
            assert len(connections) == 2
            endpoint_ids = {
                connect.xml.attrib["FromCell"]: connect.to_id for connect in connections
            }
            connector = shapes_by_id[connector_id]
            begin_id = endpoint_ids["BeginX"]
            end_id = endpoint_ids["EndX"]
            for cell_name in ("BeginX", "BeginY", "BegTrigger"):
                assert f"Sheet.{begin_id}!" in connector.cell_formula(cell_name)
            for cell_name in ("EndX", "EndY", "EndTrigger"):
                assert f"Sheet.{end_id}!" in connector.cell_formula(cell_name)
        assert page.width == pytest.approx(layout.page.width)
        assert page.height == pytest.approx(layout.page.height)
