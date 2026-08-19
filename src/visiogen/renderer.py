"""Template-based VSDX rendering."""

from __future__ import annotations

import copy
import io
import re
import threading
from collections.abc import Collection
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from xml.etree import ElementTree as ET

import vsdx.vsdxfile as vsdxfile_module
from vsdx import Connect, Page, Shape, VisioFile, namespace, r_namespace, vt_namespace

from visiogen.layout import LayoutResult
from visiogen.models import DiagramNode
from visiogen.shape_mapper import (
    EdgeVisualSpec,
    PRODUCTION_TEMPLATE_MARKERS,
    map_edge_visual,
    map_node_visual,
)


TEMPLATE_PAGE_NAME = "Template Palette"
TEMPLATE_MARKERS = (
    "__template_process__",
    "__template_component_rectangle__",
    "__template_subsystem_container__",
    "__template_reference_callout__",
    "__template_connector__",
)
GENERATED_LABELS = {
    "__template_process__": "Generated Process",
    "__template_component_rectangle__": "Generated Component",
    "__template_subsystem_container__": "Generated Subsystem",
    "__template_reference_callout__": "101",
    "__template_connector__": "feeds",
}
GENERATED_POSITIONS = {
    "__template_process__": (2.5, 5.0),
    "__template_component_rectangle__": (7.5, 5.0),
    "__template_subsystem_container__": (5.0, 2.0),
    "__template_reference_callout__": (8.5, 3.5),
    "__template_connector__": (5.0, 5.0),
}
_XML_SERIALIZATION_LOCK = threading.Lock()
_LINE_PATTERNS = {"solid": "1", "dashed": "2", "dotted": "3"}
_ARROW_STYLE = "4"


class TemplateValidationError(ValueError):
    """Raised when the canonical Visio template violates its contract."""


class RenderingError(ValueError):
    """Raised when a positioned graph cannot be rendered safely."""


@dataclass(frozen=True)
class TemplatePart:
    """A marker-bearing shape and the top-level object that contains it."""

    marker: str
    shape: Shape
    label_shape: Shape

    @property
    def text(self) -> str:
        return self.label_shape.text.strip()


@dataclass
class TemplatePalette:
    """An open canonical Visio template and its validated palette objects."""

    document: VisioFile
    page: Page
    shapes: dict[str, TemplatePart]

    def __enter__(self) -> TemplatePalette:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.document.close_vsdx()


def _top_level_shape(shape: Shape) -> Shape:
    current = shape
    while isinstance(current.parent, Shape) and current.parent.ID is not None:
        current = current.parent
    return current


def load_template_palette(
    path: str | Path,
    *,
    markers: Collection[str] = TEMPLATE_MARKERS,
) -> TemplatePalette:
    """Open and validate requested objects from the canonical Visio template."""

    document = VisioFile(str(path))
    page = document.get_page_by_name(TEMPLATE_PAGE_NAME)
    if page is None:
        document.close_vsdx()
        raise TemplateValidationError(
            f"Template must contain page {TEMPLATE_PAGE_NAME!r}"
        )

    parts: dict[str, TemplatePart] = {}
    for marker in sorted(markers):
        matches = [shape for shape in page.all_shapes if shape.text.strip() == marker]
        if len(matches) != 1:
            document.close_vsdx()
            raise TemplateValidationError(
                f"Expected exactly one {marker!r} marker; found {len(matches)}"
            )
        label_shape = matches[0]
        parts[marker] = TemplatePart(
            marker=marker,
            shape=_top_level_shape(label_shape),
            label_shape=label_shape,
        )

    return TemplatePalette(document=document, page=page, shapes=parts)


def _find_marker_shape(shape: Shape, marker: str) -> Shape:
    candidates = [shape, *shape.all_shapes]
    matches = [candidate for candidate in candidates if candidate.text.strip() == marker]
    if len(matches) != 1:
        raise TemplateValidationError(
            f"Copied object must contain exactly one {marker!r} marker; "
            f"found {len(matches)}"
        )
    return matches[0]


def _retarget_sheet_references(shape: Shape, id_map: dict[str, str]) -> None:
    """Retarget external ShapeSheet formulas after copying an object."""

    pattern = re.compile(r"Sheet\.(\d+)!")
    for cell in shape.xml.iter(f"{namespace}Cell"):
        formula = cell.attrib.get("F")
        if formula is None:
            continue

        def replace(match: re.Match[str]) -> str:
            old_id = match.group(1)
            return f"Sheet.{id_map.get(old_id, old_id)}!"

        cell.attrib["F"] = pattern.sub(replace, formula)


def _copy_shape_tree(shape: Shape, page: Page) -> Shape:
    """Copy a complete shape tree with unique IDs for every nested shape."""

    page.set_max_ids()
    copied_xml = copy.deepcopy(shape.xml)
    id_map: dict[str, str] = {}
    for element in copied_xml.iter(f"{namespace}Shape"):
        old_id = element.attrib.get("ID")
        page.max_id += 1
        new_id = str(page.max_id)
        element.attrib["ID"] = new_id
        if old_id is not None:
            id_map[old_id] = new_id

    shapes_element = page.xml.find(f"{namespace}Shapes")
    if shapes_element is None:
        raise TemplateValidationError("Template page does not contain a Shapes element")
    shapes_element.append(copied_xml)

    copied_shape = Shape(xml=copied_xml, parent=page._shapes[0], page=page)
    _retarget_sheet_references(copied_shape, id_map)
    return copied_shape


def _attach_callout_leader(callout: Shape, target: Shape) -> None:
    """Point a copied callout's leader at the bottom edge of its target shape."""

    local_x = target.x - callout.x + float(callout.cell_value("LocPinX"))
    local_y = (
        target.y
        - target.height / 2
        - callout.y
        + float(callout.cell_value("LocPinY"))
    )
    point = f"PNT({local_x:.15g},{local_y:.15g})"

    user_section = callout.xml.find(f"{namespace}Section[@N='User']")
    geometry = callout.xml.find(f"{namespace}Section[@N='Geometry'][@IX='0']")
    if user_section is None or geometry is None:
        raise TemplateValidationError("Template callout lacks target or leader geometry")

    target_cell = user_section.find(
        f"{namespace}Row[@N='msvSDTargetIntersection']/{namespace}Cell[@N='Value']"
    )
    leader_cell = user_section.find(
        f"{namespace}Row[@N='LeaderEnd']/{namespace}Cell[@N='Value']"
    )
    leader_row = geometry.find(f"{namespace}Row[@T='LineTo'][@IX='2']")
    if target_cell is None or leader_cell is None or leader_row is None:
        raise TemplateValidationError("Template callout lacks a usable leader endpoint")

    leader_x = leader_row.find(f"{namespace}Cell[@N='X']")
    leader_y = leader_row.find(f"{namespace}Cell[@N='Y']")
    if leader_x is None or leader_y is None:
        raise TemplateValidationError("Template callout leader lacks X/Y cells")

    target_formula = (
        f"PNT(Sheet.{target.ID}!PinX-PinX+LocPinX,"
        f"Sheet.{target.ID}!PinY-Sheet.{target.ID}!Height/2-PinY+LocPinY)"
    )
    target_cell.attrib.update({"V": point, "F": target_formula})
    leader_cell.attrib["V"] = point
    leader_x.attrib["V"] = f"{local_x:.15g}"
    leader_y.attrib["V"] = f"{local_y:.15g}"


def _copy_connector_connections(
    page: Page,
    source_connector: Shape,
    copied_connector: Shape,
    id_map: dict[str, str],
) -> None:
    """Copy Visio Connect rows for a copied, template-derived connector."""

    for connection in source_connector.connects:
        if connection.from_id != source_connector.ID:
            continue
        connection_xml = copy.deepcopy(connection.xml)
        connection_xml.attrib["FromSheet"] = copied_connector.ID
        connection_xml.attrib["ToSheet"] = id_map[connection.to_id]
        page.add_connect(Connect(xml=connection_xml, page=page))


def _set_local_cell_value(shape: Shape, name: str, value: str) -> None:
    """Set an explicit ShapeSheet value without inherited template formulas."""

    with redirect_stdout(io.StringIO()):
        shape.set_cell_value(name, value)
    shape.cells[name].xml.attrib.pop("F", None)


def _style_connector(shape: Shape, visual: EdgeVisualSpec) -> None:
    _set_local_cell_value(shape, "BeginArrow", _ARROW_STYLE if visual.begin_arrow else "0")
    _set_local_cell_value(shape, "EndArrow", _ARROW_STYLE if visual.end_arrow else "0")
    _set_local_cell_value(shape, "LinePattern", _LINE_PATTERNS[visual.line_style])
    _set_local_cell_value(shape, "LineWeight", f"{visual.line_weight / 72.0:.15g}")
    _set_local_cell_value(shape, "LineColor", "#000000")


def _remove_template_palette(palette: TemplatePalette) -> None:
    """Remove the source palette objects and their connections from the output page."""

    shapes_element = palette.page.xml.find(f"{namespace}Shapes")
    if shapes_element is None:
        raise TemplateValidationError("Template page does not contain a Shapes element")

    source_shapes = {part.shape.xml for part in palette.shapes.values()}
    source_ids = {part.shape.ID for part in palette.shapes.values()}
    for shape_xml in source_shapes:
        shapes_element.remove(shape_xml)

    connects_element = palette.page.xml.find(f"{namespace}Connects")
    if connects_element is not None:
        for connect_xml in list(connects_element):
            if (
                connect_xml.attrib.get("FromSheet") in source_ids
                or connect_xml.attrib.get("ToSheet") in source_ids
            ):
                connects_element.remove(connect_xml)


def _namespace_safe_xml_to_file(
    xml: ET.ElementTree,
    filename: str,
    zip_file_contents: dict[str, io.BytesIO],
) -> None:
    """Serialize each package part with its root namespace as the default."""

    root = xml.getroot()
    if root is not None and root.tag.startswith("{"):
        root_namespace = root.tag[1:].split("}", 1)[0]
        ET.register_namespace("", root_namespace)
    ET.register_namespace("r", r_namespace[1:-1])
    ET.register_namespace("vt", vt_namespace[1:-1])

    stream = io.BytesIO()
    xml.write(stream, xml_declaration=True, method="xml", encoding="UTF-8")
    zip_file_contents[filename] = io.BytesIO(stream.getvalue())


def _save_vsdx(document: VisioFile, destination: Path) -> None:
    """Save while working around vsdx 0.6.1's global namespace registry bug."""

    with _XML_SERIALIZATION_LOCK:
        original = vsdxfile_module.xml_to_file
        vsdxfile_module.xml_to_file = _namespace_safe_xml_to_file
        try:
            document.save_vsdx(str(destination))
        finally:
            vsdxfile_module.xml_to_file = original


def _node_geometry(node: DiagramNode) -> tuple[float, float, float, float]:
    if node.x is None or node.y is None or node.width is None or node.height is None:
        raise RenderingError(f"geometry required for node '{node.id}'")
    return node.x, node.y, node.width, node.height


def render_layout(
    template_path: str | Path,
    layout: LayoutResult,
    output_path: str | Path,
    *,
    automatic_reference_numbers: bool = False,
) -> Path:
    """Render positioned canonical nodes into an editable template-derived VSDX."""

    source = Path(template_path)
    destination = Path(output_path)
    if source.resolve() == destination.resolve():
        raise ValueError("Refusing to overwrite the canonical template")
    destination.parent.mkdir(parents=True, exist_ok=True)

    ordered_nodes = sorted(
        enumerate(layout.graph.nodes),
        key=lambda item: (
            not map_node_visual(item[1].type).container_capable,
            item[0],
        ),
    )
    with load_template_palette(source, markers=PRODUCTION_TEMPLATE_MARKERS) as palette:
        node_shapes: dict[str, Shape] = {}
        for _, node in ordered_nodes:
            x, y, width, height = _node_geometry(node)
            visual = map_node_visual(
                node.type,
                available_markers=palette.shapes.keys(),
            )
            copied_shape = _copy_shape_tree(
                palette.shapes[visual.marker].shape,
                palette.page,
            )
            _find_marker_shape(copied_shape, visual.marker).text = node.label
            copied_shape.width = width
            copied_shape.height = height
            copied_shape.x = x
            copied_shape.y = y
            node_shapes[node.id] = copied_shape

        callout_marker = "__template_reference_callout__"
        component_marker = "__template_component_rectangle__"
        for index, node in enumerate(layout.graph.nodes, start=1):
            reference_number = node.reference_number
            if reference_number is None and automatic_reference_numbers:
                reference_number = str(index)
            if reference_number is None:
                continue
            target = node_shapes[node.id]
            callout = _copy_shape_tree(
                palette.shapes[callout_marker].shape,
                palette.page,
            )
            _find_marker_shape(callout, callout_marker).text = reference_number
            desired_x = target.x + target.width / 2 + callout.width / 2 + 0.25
            desired_y = target.y + target.height / 2
            callout.x = min(
                max(desired_x, callout.width / 2),
                layout.page.width - callout.width / 2,
            )
            callout.y = min(
                max(desired_y, callout.height / 2),
                layout.page.height - callout.height / 2,
            )
            _retarget_sheet_references(
                callout,
                {palette.shapes[component_marker].shape.ID: target.ID},
            )
            _attach_callout_leader(callout, target)

        connector_marker = "__template_connector__"
        process_marker = "__template_process__"
        for edge in layout.graph.edges:
            try:
                source_shape = node_shapes[edge.source]
                target_shape = node_shapes[edge.target]
            except KeyError as exc:
                raise RenderingError(
                    f"edge references missing rendered endpoint '{exc.args[0]}'"
                ) from exc
            visual = map_edge_visual(
                edge.relation,
                edge.direction,
                line_style=edge.style,
                available_markers=palette.shapes.keys(),
            )
            source_connector = palette.shapes[connector_marker].shape
            connector = _copy_shape_tree(source_connector, palette.page)
            _find_marker_shape(connector, connector_marker).text = edge.label or ""
            id_map = {
                palette.shapes[process_marker].shape.ID: source_shape.ID,
                palette.shapes[component_marker].shape.ID: target_shape.ID,
            }
            _retarget_sheet_references(connector, id_map)
            _copy_connector_connections(
                page=palette.page,
                source_connector=source_connector,
                copied_connector=connector,
                id_map=id_map,
            )
            with redirect_stdout(io.StringIO()):
                connector.set_start_and_finish(
                    source_shape.center_x_y,
                    target_shape.center_x_y,
                )
            _style_connector(connector, visual)

        palette.page.width = layout.page.width
        palette.page.height = layout.page.height
        _remove_template_palette(palette)
        _save_vsdx(palette.document, destination)

    return destination


def render_feasibility_spike(
    template_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Copy and relabel all five palette objects into a generated VSDX artifact."""

    source = Path(template_path)
    destination = Path(output_path)
    if source.resolve() == destination.resolve():
        raise ValueError("Refusing to overwrite the canonical template")
    destination.parent.mkdir(parents=True, exist_ok=True)

    with load_template_palette(source) as palette:
        copies: dict[str, Shape] = {}
        for marker in TEMPLATE_MARKERS:
            copied_shape = _copy_shape_tree(
                palette.shapes[marker].shape,
                palette.page,
            )
            copied_label = _find_marker_shape(copied_shape, marker)
            copied_label.text = GENERATED_LABELS[marker]
            copied_shape.x, copied_shape.y = GENERATED_POSITIONS[marker]
            copies[marker] = copied_shape

        process_marker = "__template_process__"
        component_marker = "__template_component_rectangle__"
        connector_marker = "__template_connector__"
        id_map = {
            palette.shapes[process_marker].shape.ID: copies[process_marker].ID,
            palette.shapes[component_marker].shape.ID: copies[component_marker].ID,
        }
        copied_connector = copies[connector_marker]
        _retarget_sheet_references(copied_connector, id_map)
        _retarget_sheet_references(
            copies["__template_reference_callout__"],
            id_map,
        )
        _attach_callout_leader(
            copies["__template_reference_callout__"],
            copies[component_marker],
        )
        _copy_connector_connections(
            page=palette.page,
            source_connector=palette.shapes[connector_marker].shape,
            copied_connector=copied_connector,
            id_map=id_map,
        )
        with redirect_stdout(io.StringIO()):
            copied_connector.set_start_and_finish(
                copies[process_marker].center_x_y,
                copies[component_marker].center_x_y,
            )

        _remove_template_palette(palette)
        _save_vsdx(palette.document, destination)

    return destination
