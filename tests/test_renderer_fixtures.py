import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from vsdx import Shape, VisioFile, namespace

from visiogen.layouts.graphviz_layout import GraphvizLayout
from visiogen.models import DiagramGraph
from visiogen.renderer import render_layout
from visiogen.shape_mapper import PRODUCTION_TEMPLATE_MARKERS, map_edge_visual


PROJECT_ROOT = Path(__file__).parents[1]
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "template.vsdx"
FIXTURE_PATHS = (
    PROJECT_ROOT / "tests" / "fixtures" / "graphs" / "expected" / "linear_flow.json",
    PROJECT_ROOT / "tests" / "fixtures" / "graphs" / "expected" / "basic_system.json",
    PROJECT_ROOT / "tests" / "fixtures" / "graphs" / "renderer" / "headphone.json",
)


def _outer_shape(shape: Shape) -> Shape:
    current = shape
    while isinstance(current.parent, Shape) and current.parent.ID is not None:
        current = current.parent
    return current


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
        node_shapes: dict[str, Shape] = {}
        for node in layout.graph.nodes:
            label_shape = next(
                shape for shape in page.all_shapes if shape.text.strip() == node.label
            )
            outer = _outer_shape(label_shape)
            node_shapes[node.id] = outer
            assert outer in page.child_shapes
            assert outer.x == pytest.approx(node.x)
            assert outer.y == pytest.approx(node.y)
            assert outer.width == pytest.approx(node.width)
            assert outer.height == pytest.approx(node.height)

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

        line_patterns = {"solid": "1", "dashed": "2", "dotted": "3"}
        for edge in layout.graph.edges:
            source_id = node_shapes[edge.source].ID
            target_id = node_shapes[edge.target].ID
            matching_connectors = []
            for connector_id in connector_ids:
                rows = [
                    connect for connect in page.connects if connect.from_id == connector_id
                ]
                endpoints = {
                    connect.xml.attrib["FromCell"]: connect.to_id for connect in rows
                }
                if endpoints == {"BeginX": source_id, "EndX": target_id}:
                    matching_connectors.append(shapes_by_id[connector_id])
            assert len(matching_connectors) == 1
            connector = matching_connectors[0]
            visual = map_edge_visual(
                edge.relation,
                edge.direction,
                line_style=edge.style if "style" in edge.model_fields_set else None,
            )
            assert connector.cell_value("BeginArrow") == (
                "4" if visual.begin_arrow else "0"
            )
            assert connector.cell_value("EndArrow") == (
                "4" if visual.end_arrow else "0"
            )
            assert connector.cell_value("LinePattern") == line_patterns[
                visual.line_style
            ]
            assert float(connector.cell_value("LineWeight")) * 72 == pytest.approx(
                visual.line_weight
            )
            assert connector.cell_value("LineColor") == "#000000"

        for node in layout.graph.nodes:
            if node.reference_number is None:
                continue
            label_shape = next(
                shape
                for shape in page.all_shapes
                if shape.text.strip() == node.reference_number
            )
            callout = _outer_shape(label_shape)
            target = node_shapes[node.id]
            relationships = callout.cells["Relationships"].formula
            assert f"Sheet.{target.ID}!" in relationships
            user_section = callout.xml.find(f"{namespace}Section[@N='User']")
            target_formula = user_section.find(
                f"{namespace}Row[@N='msvSDTargetIntersection']/"
                f"{namespace}Cell[@N='Value']"
            ).attrib["F"]
            leader_formula = user_section.find(
                f"{namespace}Row[@N='LeaderEnd']/{namespace}Cell[@N='Value']"
            ).attrib["F"]
            leader_geometry = callout.xml.find(
                f"{namespace}Section[@N='Geometry'][@IX='0']/"
                f"{namespace}Row[@T='LineTo'][@IX='2']"
            )
            assert f"Sheet.{target.ID}!" in target_formula
            assert leader_formula == "User.msvSDTargetIntersection"
            assert (
                leader_geometry.find(f"{namespace}Cell[@N='X']").attrib["F"]
                == "User.LeaderEnd"
            )
            assert (
                leader_geometry.find(f"{namespace}Cell[@N='Y']").attrib["F"]
                == "User.LeaderEnd"
            )
            assert callout.x - callout.width / 2 >= -1e-9
            assert callout.y - callout.height / 2 >= -1e-9
            assert callout.x + callout.width / 2 <= page.width + 1e-9
            assert callout.y + callout.height / 2 <= page.height + 1e-9
            text_center_x = (
                callout.x
                - float(callout.cell_value("LocPinX"))
                + float(callout.cell_value("TxtPinX"))
            )
            text_center_y = (
                callout.y
                - float(callout.cell_value("LocPinY"))
                + float(callout.cell_value("TxtPinY"))
            )
            text_width = float(callout.cell_value("TxtWidth"))
            text_height = float(callout.cell_value("TxtHeight"))
            overlap_width = max(
                0.0,
                min(
                    text_center_x + text_width / 2,
                    target.x + target.width / 2,
                )
                - max(
                    text_center_x - text_width / 2,
                    target.x - target.width / 2,
                ),
            )
            overlap_height = max(
                0.0,
                min(
                    text_center_y + text_height / 2,
                    target.y + target.height / 2,
                )
                - max(
                    text_center_y - text_height / 2,
                    target.y - target.height / 2,
                ),
            )
            assert overlap_width * overlap_height == pytest.approx(0.0, abs=1e-9)
        assert page.width == pytest.approx(layout.page.width)
        assert page.height == pytest.approx(layout.page.height)
