"""Template-based VSDX rendering."""

from __future__ import annotations

import copy
import io
import math
import os
import re
import tempfile
import threading
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from xml.etree import ElementTree as ET

from vsdx import (
    Cell,
    Connect,
    Page,
    Shape,
    VisioFile,
    namespace,
    r_namespace,
    vt_namespace,
)

from visiogen.generation.compiler import (
    IRCallout,
    IRConnector,
    IRPoint,
    IRPort,
    IRShape,
    RendererIR,
)
from visiogen.layout import LayoutResult
from visiogen.models import DiagramNode
from visiogen.shape_mapper import (
    PRODUCTION_TEMPLATE_MARKERS,
    EdgeVisualSpec,
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
_REFERENCE_TEXT_WIDTH = 0.4
_REFERENCE_TEXT_HEIGHT = 0.25
_REFERENCE_GAP = 0.05


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


def _strip_inherited_dimension_caches(shape: Shape) -> None:
    """Remove stale palette-instance caches that depend on shape dimensions.

    The template palette objects are resized instances of native masters. Visio
    writes calculated values for inherited Geometry, Scratch, Control, and User
    cells into page XML with ``F="Inh"``. Copying those rows and then changing
    only Width/Height leaves the old palette outline in the package, even though
    the generated shape and its ports have the requested dimensions.

    Removing only inherited cells restores the linked master's formulas in the
    context of the generated instance. Renderer-authored values, formulas, and
    deletion overrides are deliberately preserved.
    """

    dimension_sections = {"Geometry", "Scratch", "Control", "User"}
    for section in list(shape.xml.findall(f"{namespace}Section")):
        if section.attrib.get("N") not in dimension_sections:
            continue
        for cell in list(section.findall(f"{namespace}Cell")):
            if cell.attrib.get("F") == "Inh":
                section.remove(cell)
        for row in list(section.findall(f"{namespace}Row")):
            row_cells = list(row.findall(f"{namespace}Cell"))
            for cell in row_cells:
                if cell.attrib.get("F") == "Inh":
                    row.remove(cell)
            if (
                row_cells
                and not row.findall(f"{namespace}Cell")
                and row.attrib.get("Del") != "1"
            ):
                section.remove(row)
        if not list(section) and section.attrib.get("Del") != "1":
            shape.xml.remove(section)
    for child in shape.child_shapes:
        _strip_inherited_dimension_caches(child)


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
    leader_cell.attrib.update(
        {"V": point, "F": "User.msvSDTargetIntersection"}
    )
    leader_x.attrib.update(
        {"V": f"{local_x:.15g}", "F": "User.LeaderEnd"}
    )
    leader_y.attrib.update(
        {"V": f"{local_y:.15g}", "F": "User.LeaderEnd"}
    )


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
        connection_xml.attrib["ToCell"] = "PinX"
        connection_xml.attrib["ToPart"] = "3"
        page.add_connect(Connect(xml=connection_xml, page=page))


def _set_local_cell_value(shape: Shape, name: str, value: str) -> None:
    """Set a local ShapeSheet value without mutating stdout or a master shape."""

    cell = shape.cells.get(name)
    if cell is None:
        master_cell_xml = None
        if shape.master_page_ID is not None and shape.master_shape is not None:
            master_cell_xml = shape.master_shape.xml.find(f'{namespace}Cell[@N="{name}"]')
        cell_xml = (
            copy.deepcopy(master_cell_xml)
            if master_cell_xml is not None
            else ET.Element(f"{namespace}Cell", {"N": name})
        )
        cell = Cell(xml=cell_xml, shape=shape)
        shape.cells[name] = cell
        local_cells = shape.xml.findall(f"{namespace}Cell")
        insertion_index = (
            list(shape.xml).index(local_cells[-1]) + 1 if local_cells else 0
        )
        shape.xml.insert(insertion_index, cell_xml)
    cell.value = value
    cell.xml.attrib.pop("F", None)


def _set_local_cell_formula(
    shape: Shape,
    name: str,
    value: str,
    formula: str,
) -> None:
    """Materialize a local ShapeSheet result and its recalculating formula."""

    _set_local_cell_value(shape, name, value)
    shape.cells[name].xml.attrib["F"] = formula


def _place_reference_callout(
    callout: Shape,
    target: Shape,
    page_width: float,
    page_height: float,
) -> None:
    """Place a compact numeral carrier beside its target without obscuring it."""

    text_width = min(_REFERENCE_TEXT_WIDTH, callout.width)
    text_height = min(
        _REFERENCE_TEXT_HEIGHT,
        float(callout.cell_value("TxtHeight")),
        callout.height,
    )
    target_left = target.x - target.width / 2
    target_right = target.x + target.width / 2
    target_bottom = target.y - target.height / 2
    target_top = target.y + target.height / 2
    candidates = (
        (target_right + _REFERENCE_GAP + text_width / 2, target.y),
        (target_left - _REFERENCE_GAP - text_width / 2, target.y),
        (target.x, target_top + _REFERENCE_GAP + text_height / 2),
        (target.x, target_bottom - _REFERENCE_GAP - text_height / 2),
    )

    root_x_min = callout.width / 2
    root_x_max = page_width - callout.width / 2
    root_y_min = callout.height / 2
    root_y_max = page_height - callout.height / 2
    loc_pin_x = float(callout.cell_value("LocPinX"))
    loc_pin_y = float(callout.cell_value("LocPinY"))

    for text_x, text_y in candidates:
        if (
            text_x - text_width / 2 < 0
            or text_x + text_width / 2 > page_width
            or text_y - text_height / 2 < 0
            or text_y + text_height / 2 > page_height
        ):
            continue

        root_x_low = max(
            root_x_min,
            text_x + text_width / 2 - callout.width / 2,
        )
        root_x_high = min(
            root_x_max,
            text_x - text_width / 2 + callout.width / 2,
        )
        root_y_low = max(
            root_y_min,
            text_y + text_height / 2 - callout.height / 2,
        )
        root_y_high = min(
            root_y_max,
            text_y - text_height / 2 + callout.height / 2,
        )
        if root_x_low > root_x_high or root_y_low > root_y_high:
            continue

        root_x = min(max(text_x, root_x_low), root_x_high)
        root_y = min(max(text_y, root_y_low), root_y_high)
        _set_local_cell_value(callout, "PinX", repr(root_x))
        _set_local_cell_value(callout, "PinY", repr(root_y))
        _set_local_cell_value(callout, "TxtWidth", repr(text_width))
        _set_local_cell_value(callout, "TxtHeight", repr(text_height))
        _set_local_cell_value(
            callout,
            "TxtPinX",
            repr(text_x - root_x + loc_pin_x),
        )
        _set_local_cell_value(
            callout,
            "TxtPinY",
            repr(text_y - root_y + loc_pin_y),
        )
        return

    raise RenderingError(
        f"reference callout cannot avoid target {target.ID} inside page bounds"
    )


def _set_connector_cached_geometry(
    shape: Shape,
    start: tuple[float, float],
    finish: tuple[float, float],
) -> None:
    """Write coherent one-dimensional connector endpoint and transform caches."""

    begin_x, begin_y = start
    end_x, end_y = finish
    delta_x = end_x - begin_x
    delta_y = end_y - begin_y
    values = {
        "BeginX": begin_x,
        "BeginY": begin_y,
        "EndX": end_x,
        "EndY": end_y,
    }
    for name, value in values.items():
        cell = shape.cells.get(name)
        if cell is None:
            _set_local_cell_value(shape, name, f"{value:.15g}")
        else:
            cell.value = f"{value:.15g}"

    axis_specs = (
        ("X", begin_x, end_x, delta_x),
        ("Y", begin_y, end_y, delta_y),
    )
    for axis, begin, end, delta in axis_specs:
        if abs(delta) <= 1e-12:
            dimension = 0.25
            pin = begin
            pin_formula = f"GUARD(Begin{axis})"
            dimension_formula = "GUARD(0.25DL)"
        else:
            dimension = delta
            pin = (begin + end) / 2
            pin_formula = f"GUARD((Begin{axis}+End{axis})/2)"
            dimension_formula = f"GUARD(End{axis}-Begin{axis})"
        _set_local_cell_formula(
            shape,
            f"Pin{axis}",
            f"{pin:.15g}",
            pin_formula,
        )
        _set_local_cell_formula(
            shape,
            "Width" if axis == "X" else "Height",
            f"{dimension:.15g}",
            dimension_formula,
        )
        _set_local_cell_formula(
            shape,
            f"LocPin{axis}",
            f"{dimension / 2:.15g}",
            f"GUARD({'Width' if axis == 'X' else 'Height'}/2)",
        )


def _boundary_points(
    source: DiagramNode | Shape,
    target: DiagramNode | Shape,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Intersect the center line with both node bounding boxes."""

    source_geometry = (
        _node_geometry(source)
        if isinstance(source, DiagramNode)
        else (source.x, source.y, source.width, source.height)
    )
    target_geometry = (
        _node_geometry(target)
        if isinstance(target, DiagramNode)
        else (target.x, target.y, target.width, target.height)
    )
    source_x, source_y, source_width, source_height = source_geometry
    target_x, target_y, target_width, target_height = target_geometry
    source_id = source.id if isinstance(source, DiagramNode) else source.ID
    target_id = target.id if isinstance(target, DiagramNode) else target.ID
    delta_x = target_x - source_x
    delta_y = target_y - source_y
    if delta_x == 0 and delta_y == 0:
        if source_id == target_id:
            right = source_x + source_width / 2
            return (
                (right, source_y - source_height / 4),
                (right, source_y + source_height / 4),
            )
        raise RenderingError(
            f"edge endpoints '{source_id}' and '{target_id}' share one center"
        )

    def intersect(
        center_x: float,
        center_y: float,
        half_width: float,
        half_height: float,
        direction_x: float,
        direction_y: float,
    ) -> tuple[float, float]:
        scale = 1.0 / max(
            abs(direction_x) / half_width,
            abs(direction_y) / half_height,
        )
        return (
            center_x + direction_x * scale,
            center_y + direction_y * scale,
        )

    start = intersect(
        source_x,
        source_y,
        source_width / 2,
        source_height / 2,
        delta_x,
        delta_y,
    )
    finish = intersect(
        target_x,
        target_y,
        target_width / 2,
        target_height / 2,
        -delta_x,
        -delta_y,
    )
    return start, finish


def _configure_dynamic_connector_glue(
    connector: Shape,
    source: Shape,
    target: Shape,
    start: tuple[float, float],
    finish: tuple[float, float],
) -> None:
    """Glue to whole shapes so Visio chooses sane perimeter attachment points."""

    begin_x, begin_y = start
    end_x, end_y = finish
    _set_local_cell_formula(
        connector,
        "BeginX",
        f"{begin_x:.15g}",
        "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)",
    )
    _set_local_cell_formula(
        connector,
        "BeginY",
        f"{begin_y:.15g}",
        "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)",
    )
    _set_local_cell_formula(
        connector,
        "EndX",
        f"{end_x:.15g}",
        "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)",
    )
    _set_local_cell_formula(
        connector,
        "EndY",
        f"{end_y:.15g}",
        "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)",
    )
    _set_local_cell_formula(
        connector,
        "BegTrigger",
        "2",
        f"_XFTRIGGER(Sheet.{source.ID}!EventXFMod)",
    )
    _set_local_cell_formula(
        connector,
        "EndTrigger",
        "2",
        f"_XFTRIGGER(Sheet.{target.ID}!EventXFMod)",
    )
    _set_local_cell_value(connector, "ConFixedCode", "6")


def _configure_explicit_connector_glue(
    connector: Shape,
    source: Shape,
    source_port: str,
    target: Shape,
    target_port: str,
    start: tuple[float, float],
    finish: tuple[float, float],
) -> None:
    """Glue explicit route endpoints to exact named connection-point rows."""

    source_point = (
        f"PAR(PNT(Sheet.{source.ID}!Connections.{source_port}.X,"
        f"Sheet.{source.ID}!Connections.{source_port}.Y))"
    )
    target_point = (
        f"PAR(PNT(Sheet.{target.ID}!Connections.{target_port}.X,"
        f"Sheet.{target.ID}!Connections.{target_port}.Y))"
    )
    for name, value, formula in (
        ("BeginX", start[0], source_point),
        ("BeginY", start[1], source_point),
        ("EndX", finish[0], target_point),
        ("EndY", finish[1], target_point),
    ):
        _set_local_cell_formula(connector, name, f"{value:.15g}", formula)
    _set_local_cell_formula(
        connector,
        "BegTrigger",
        "2",
        f"_XFTRIGGER(Sheet.{source.ID}!EventXFMod)",
    )
    _set_local_cell_formula(
        connector,
        "EndTrigger",
        "2",
        f"_XFTRIGGER(Sheet.{target.ID}!EventXFMod)",
    )
    # Explicit routes own their geometry.  Letting Visio's routing algorithm take
    # over here can replace that geometry when an endpoint moves (and value 6 is
    # reserved for Visio's internal routing algorithm).  The endpoint formulas
    # still recalculate, so the connector remains glued while its route stays
    # under our control.
    _set_local_cell_value(connector, "ConFixedCode", "2")


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
    """Serialize a package part without mutating ElementTree's global registry."""

    root = xml.getroot()
    if root is None:
        raise RenderingError(f"cannot serialize empty XML tree for {filename}")
    root_namespace = ""
    if root.tag.startswith("{"):
        root_namespace = root.tag[1:].split("}", 1)[0]

    serialized = ET.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        short_empty_elements=True,
    ).decode("UTF-8")
    declarations = re.findall(
        r'xmlns(?::([A-Za-z_][\w.-]*))?="([^"]+)"',
        serialized,
    )
    preferred = {
        root_namespace: "",
        r_namespace[1:-1]: "r",
        vt_namespace[1:-1]: "vt",
    }
    used_prefixes = {prefix for prefix in preferred.values() if prefix}
    generated_index = 1
    for old_prefix, uri in declarations:
        desired_prefix = preferred.get(uri)
        if desired_prefix is None:
            if old_prefix and not re.fullmatch(r"ns\d+", old_prefix):
                desired_prefix = old_prefix
            else:
                while f"p{generated_index}" in used_prefixes:
                    generated_index += 1
                desired_prefix = f"p{generated_index}"
                generated_index += 1
            used_prefixes.add(desired_prefix)

        if old_prefix == desired_prefix:
            continue
        if not old_prefix:
            raise RenderingError(
                f"cannot safely remap non-root default namespace {uri!r}"
            )

        old_declaration = f'xmlns:{old_prefix}="{uri}"'
        new_declaration = (
            f'xmlns="{uri}"'
            if not desired_prefix
            else f'xmlns:{desired_prefix}="{uri}"'
        )
        serialized = serialized.replace(old_declaration, new_declaration)
        replacement = f"{desired_prefix}:" if desired_prefix else ""
        serialized = serialized.replace(f"<{old_prefix}:", f"<{replacement}")
        serialized = serialized.replace(f"</{old_prefix}:", f"</{replacement}")
        serialized = serialized.replace(f" {old_prefix}:", f" {replacement}")

    if re.search(r"(?:<|</|\s)ns\d+:", serialized):
        raise RenderingError(f"unsafe generated namespace prefix in {filename}")
    zip_file_contents[filename] = io.BytesIO(serialized.encode("UTF-8"))


def _write_document_parts(document: VisioFile) -> None:
    """Serialize changed package parts without monkey-patching the vsdx module."""

    parts: list[tuple[ET.ElementTree, str]] = [
        (
            document.pages_xml_rels,
            f"{document.directory}/visio/pages/_rels/pages.xml.rels",
        ),
        (document.pages_xml, document._pages_filename()),
    ]
    parts.extend((page.xml, page.filename) for page in document.master_pages)
    for page in document.pages:
        parts.append((page.xml, page.filename))
        if page.rels_xml_filename:
            parts.append((page.rels_xml, page.rels_xml_filename))
    parts.extend(
        [
            (
                document.content_types_xml,
                f"{document.directory}/[Content_Types].xml",
            ),
            (document.document_xml, f"{document.directory}/visio/document.xml"),
            (
                document.document_xml_rels,
                f"{document.directory}/visio/_rels/document.xml.rels",
            ),
        ]
    )
    if document.app_xml is not None:
        parts.append((document.app_xml, f"{document.directory}/docProps/app.xml"))
    for xml, filename in parts:
        _namespace_safe_xml_to_file(xml, filename, document.zip_file_contents)


def _save_vsdx(document: VisioFile, destination: Path) -> None:
    """Serialize to a private sibling, then atomically replace the destination."""

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp.vsdx",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

        with _XML_SERIALIZATION_LOCK:
            _write_document_parts(document)
            save_zip = getattr(document, "_save_zip_file_contents_to_disk")
            save_zip(str(temporary_path))
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _node_geometry(node: DiagramNode) -> tuple[float, float, float, float]:
    if node.x is None or node.y is None or node.width is None or node.height is None:
        raise RenderingError(f"geometry required for node '{node.id}'")
    geometry = (node.x, node.y, node.width, node.height)
    if not all(math.isfinite(value) for value in geometry) or min(
        node.width, node.height
    ) <= 0:
        raise RenderingError(
            f"finite coordinates and positive dimensions required for node '{node.id}'"
        )
    return geometry


def _require_distinct_output(source: Path, destination: Path) -> None:
    same_path = source.resolve() == destination.resolve()
    same_file = destination.exists() and source.samefile(destination)
    if same_path or same_file:
        raise ValueError("Refusing to overwrite the canonical template")


def _set_section_cell(
    shape: Shape,
    section_name: str,
    row_attributes: dict[str, str],
    cell_name: str,
    value: str,
) -> None:
    section = shape.xml.find(f"{namespace}Section[@N='{section_name}']")
    if section is None:
        section = ET.SubElement(shape.xml, f"{namespace}Section", {"N": section_name})
    selector = "".join(f"[@{key}='{item}']" for key, item in row_attributes.items())
    row = section.find(f"{namespace}Row{selector}")
    if row is None:
        row = ET.SubElement(section, f"{namespace}Row", row_attributes)
    cell = row.find(f"{namespace}Cell[@N='{cell_name}']")
    if cell is None:
        cell = ET.SubElement(row, f"{namespace}Cell", {"N": cell_name})
    cell.attrib["V"] = value
    cell.attrib["F"] = "No Formula"


def _block_master_inheritance(shape: Shape, names: Collection[str]) -> None:
    """Make G5 cached cell values authoritative when desktop Visio recalculates."""

    for name in names:
        cell = shape.cells.get(name)
        if cell is None:
            raise RenderingError(f"cannot block missing cell '{name}' on shape {shape.ID}")
        cell.xml.attrib["F"] = "No Formula"


def _stabilize_local_formulas(shape: Shape, names: Collection[str]) -> None:
    """Keep editable instance values local across Visio move/undo operations.

    ``No Formula`` blocks a master formula, but Visio can restore inheritance when
    undoing an edit and then use the master's original transform. A local unguarded
    numeric formula remains editable and gives undo an explicit instance value to
    restore instead.
    """

    for name in names:
        cell = shape.cells.get(name)
        if cell is None:
            raise RenderingError(f"cannot stabilize missing cell '{name}' on shape {shape.ID}")
        cell.xml.attrib["F"] = cell.xml.attrib["V"]


def _stabilize_transform_tree(shape: Shape) -> None:
    names = ("PinX", "PinY", "Width", "Height", "LocPinX", "LocPinY")
    _stabilize_local_formulas(shape, names)
    for child in shape.child_shapes:
        _stabilize_transform_tree(child)


def _resize_group_children(shape: Shape, width: float, height: float) -> None:
    """Scale copied group children to the requested instance dimensions."""

    old_width = float(shape.cell_value("Width"))
    old_height = float(shape.cell_value("Height"))
    scale_x = width / old_width
    scale_y = height / old_height
    for child in shape.child_shapes:
        child_width = float(child.cell_value("Width")) * scale_x
        child_height = float(child.cell_value("Height")) * scale_y
        _resize_group_children(child, child_width, child_height)
        for name, value in (
            ("PinX", float(child.cell_value("PinX")) * scale_x),
            ("PinY", float(child.cell_value("PinY")) * scale_y),
            ("Width", child_width),
            ("Height", child_height),
            ("LocPinX", float(child.cell_value("LocPinX")) * scale_x),
            ("LocPinY", float(child.cell_value("LocPinY")) * scale_y),
        ):
            _set_local_cell_value(child, name, f"{value:.15g}")
        _block_master_inheritance(
            child, ("PinX", "PinY", "Width", "Height", "LocPinX", "LocPinY")
        )


def _hide_shape_tree(shape: Shape) -> None:
    """Hide a copied master child and every nested descendant reliably."""

    shape.xml.attrib["Del"] = "1"
    for name in ("FillPattern", "LinePattern", "HideText"):
        _set_local_cell_value(shape, name, "0" if name != "HideText" else "1")
    geometry_indexes = {
        section.attrib.get("IX", "0")
        for section in shape.xml.findall(f"{namespace}Section[@N='Geometry']")
    }
    if shape.master_shape is not None:
        geometry_indexes.update(
            section.attrib.get("IX", "0")
            for section in shape.master_shape.xml.findall(
                f"{namespace}Section[@N='Geometry']"
            )
        )
    for index in sorted(geometry_indexes, key=int):
        section = shape.xml.find(
            f"{namespace}Section[@N='Geometry'][@IX='{index}']"
        )
        if section is None:
            section = ET.SubElement(
                shape.xml,
                f"{namespace}Section",
                {"N": "Geometry", "IX": index},
            )
        no_show = section.find(f"{namespace}Cell[@N='NoShow']")
        if no_show is None:
            no_show = ET.SubElement(section, f"{namespace}Cell", {"N": "NoShow"})
        no_show.attrib.update({"V": "1", "F": "No Formula"})
    for child in shape.child_shapes:
        _hide_shape_tree(child)


def _delete_unused_master_geometry_rows(shape: Shape, used: set[int]) -> None:
    if shape.master_shape is None:
        return
    geometry = shape.xml.find(f"{namespace}Section[@N='Geometry'][@IX='0']")
    master_geometry = shape.master_shape.xml.find(
        f"{namespace}Section[@N='Geometry'][@IX='0']"
    )
    if geometry is None or master_geometry is None:
        return
    for master_row in master_geometry.findall(f"{namespace}Row"):
        index = int(master_row.attrib["IX"])
        if index not in used:
            ET.SubElement(
                geometry,
                f"{namespace}Row",
                {"T": master_row.attrib.get("T", "LineTo"), "IX": str(index), "Del": "1"},
            )


def _replace_rectangle_geometry(shape: Shape, width: float, height: float) -> None:
    for section in shape.xml.findall(f"{namespace}Section[@N='Geometry']"):
        shape.xml.remove(section)
    geometry = ET.SubElement(
        shape.xml, f"{namespace}Section", {"N": "Geometry", "IX": "0"}
    )
    for name, value in (("NoShow", "0"), ("NoFill", "0"), ("NoLine", "0")):
        ET.SubElement(
            geometry,
            f"{namespace}Cell",
            {"N": name, "V": value, "F": "No Formula"},
        )
    for index, (row_type, x, y) in enumerate(
        (
            ("MoveTo", 0.0, 0.0),
            ("LineTo", width, 0.0),
            ("LineTo", width, height),
            ("LineTo", 0.0, height),
            ("LineTo", 0.0, 0.0),
        ),
        start=1,
    ):
        row = ET.SubElement(
            geometry, f"{namespace}Row", {"T": row_type, "IX": str(index)}
        )
        ET.SubElement(row, f"{namespace}Cell", {"N": "X", "V": f"{x:.15g}"})
        ET.SubElement(row, f"{namespace}Cell", {"N": "Y", "V": f"{y:.15g}"})
    _delete_unused_master_geometry_rows(shape, {1, 2, 3, 4, 5})
    if shape.master_shape is None:
        return
    inherited_indexes = sorted(
        {
            section.attrib.get("IX", "0")
            for section in shape.master_shape.xml.findall(
                f"{namespace}Section[@N='Geometry']"
            )
            if section.attrib.get("IX", "0") != "0"
        },
        key=int,
    )
    for index in inherited_indexes:
        hidden = ET.SubElement(
            shape.xml,
            f"{namespace}Section",
            {"N": "Geometry", "IX": index},
        )
        ET.SubElement(
            hidden,
            f"{namespace}Cell",
            {"N": "NoShow", "V": "1", "F": "No Formula"},
        )


def _replace_container_body(shape: Shape, header: Shape, width: float, height: float) -> None:
    """Render the housing body on the group root, independent of master internals."""

    shapes = shape.xml.find(f"{namespace}Shapes")
    if shapes is None:
        raise RenderingError(f"container shape {shape.ID} has no child Shapes element")
    header_root = header
    while (
        isinstance(header_root.parent, Shape)
        and header_root.parent.ID != shape.ID
    ):
        header_root = header_root.parent
    for child in list(shape.child_shapes):
        if child.ID != header_root.ID:
            _hide_shape_tree(child)
    _replace_rectangle_geometry(shape, width, height)


def _to_visio_point(page_height: float, point: IRPoint) -> tuple[float, float]:
    return point.x, page_height - point.y


def _shape_geometry(
    page_height: float, shape: IRShape
) -> tuple[float, float, float, float]:
    return (
        shape.rect.x + shape.rect.width / 2,
        page_height - shape.rect.y - shape.rect.height / 2,
        shape.rect.width,
        shape.rect.height,
    )


def _style_ir_shape(shape: Shape, plan: IRShape) -> None:
    _set_local_cell_value(shape, "FillForegnd", plan.style.fill_color)
    _set_local_cell_value(shape, "LineColor", plan.style.line_color)
    _set_local_cell_value(shape, "LineWeight", f"{plan.style.line_weight_pt / 72:.15g}")
    _set_local_cell_value(shape, "LinePattern", _LINE_PATTERNS[plan.style.line_pattern])


def _contrasting_text_color(background: str) -> str:
    channels = [int(background[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    black_contrast = (luminance + 0.05) / 0.05
    white_contrast = 1.05 / (luminance + 0.05)
    return "#000000" if black_contrast >= white_contrast else "#FFFFFF"


def _configure_ir_text(
    label_shape: Shape,
    owner: IRShape,
    page_height: float,
) -> None:
    owner_bottom = page_height - owner.rect.y - owner.rect.height
    text_center_x = owner.text_box.x + owner.text_box.width / 2
    text_center_y = page_height - owner.text_box.y - owner.text_box.height / 2
    _set_local_cell_value(
        label_shape, "TxtPinX", f"{text_center_x - owner.rect.x:.15g}"
    )
    _set_local_cell_value(
        label_shape, "TxtPinY", f"{text_center_y - owner_bottom:.15g}"
    )
    _set_local_cell_value(label_shape, "TxtWidth", f"{owner.text_box.width:.15g}")
    _set_local_cell_value(label_shape, "TxtHeight", f"{owner.text_box.height:.15g}")
    _set_local_cell_value(
        label_shape, "TxtLocPinX", f"{owner.text_box.width / 2:.15g}"
    )
    _set_local_cell_value(
        label_shape, "TxtLocPinY", f"{owner.text_box.height / 2:.15g}"
    )
    _set_local_cell_value(
        label_shape,
        "VerticalAlign",
        {"top": "0", "middle": "1", "bottom": "2"}[owner.typography.vertical_align],
    )
    style = (1 if owner.typography.bold else 0) + (2 if owner.typography.italic else 0)
    for name, value in (
        ("Font", owner.typography.family),
        ("Size", f"{owner.typography.size_pt / 72:.15g}"),
        ("Color", owner.typography.color),
        ("Style", str(style)),
    ):
        _set_section_cell(label_shape, "Character", {"IX": "0"}, name, value)
    _set_section_cell(
        label_shape,
        "Paragraph",
        {"IX": "0"},
        "HorzAlign",
        {"left": "0", "center": "1", "right": "2"}[owner.typography.horizontal_align],
    )


def _replace_connection_points(shape: Shape, plan: IRShape, page_height: float) -> None:
    existing = shape.xml.find(f"{namespace}Section[@N='Connection']")
    if existing is not None:
        shape.xml.remove(existing)
    section = ET.SubElement(shape.xml, f"{namespace}Section", {"N": "Connection"})
    owner_bottom = page_height - plan.rect.y - plan.rect.height
    # DirX/DirY is the *inward* alignment vector for a Type=0 connection
    # point.  Reversing these signs tells Visio to approach a port through the
    # shape itself, which produces the long loop-back routes seen after moving
    # a connected shape.
    direction = {
        "top": ("0", "-1"),
        "right": ("-1", "0"),
        "bottom": ("0", "1"),
        "left": ("1", "0"),
    }
    for port in plan.ports:
        row = ET.SubElement(
            section,
            f"{namespace}Row",
            {"N": port.name, "T": "Connection"},
        )
        local_x = port.x - plan.rect.x
        local_y = page_height - port.y - owner_bottom
        x_fraction = local_x / plan.rect.width
        y_fraction = local_y / plan.rect.height
        x_formula, y_formula = _connection_point_formulas(
            plan,
            port,
            x_fraction,
            y_fraction,
        )
        direction_x, direction_y = direction[port.side]
        for name, value, formula in (
            ("X", f"{local_x:.15g}", x_formula),
            ("Y", f"{local_y:.15g}", y_formula),
            ("DirX", direction_x, None),
            ("DirY", direction_y, None),
            ("Type", "0", None),
        ):
            attributes = {"N": name, "V": value}
            if formula is not None:
                attributes["F"] = formula
            ET.SubElement(row, f"{namespace}Cell", attributes)


def _connection_point_formulas(
    plan: IRShape,
    port: IRPort,
    x_fraction: float,
    y_fraction: float,
) -> tuple[str, str]:
    """Keep projected connection points on the master silhouette after resize."""

    x_formula = f"Width*{x_fraction:.15g}"
    y_formula = f"Height*{y_fraction:.15g}"
    if port.side in {"top", "bottom"}:
        offset = (port.x - plan.rect.x) / plan.rect.width
    else:
        offset = (port.y - plan.rect.y) / plan.rect.height
    if plan.master_marker == "__template_terminator__":
        radius = "MIN(Height/2,Width/4)"
        if port.side in {"left", "right"}:
            curve = math.sqrt(max(1.0 - (1.0 - 2.0 * offset) ** 2, 0.0))
            inset = f"{1.0 - curve:.15g}"
            x_formula = (
                f"{radius}*{inset}"
                if port.side == "left"
                else f"Width-{radius}*{inset}"
            )
            y_formula = f"Height*{1.0 - offset:.15g}"
        else:
            position = f"Width*{offset:.15g}"
            sign = "+" if port.side == "top" else "-"
            left_curve = (
                f"Height/2{sign}Height/2*SQRT(1-(({position}-{radius})/"
                f"{radius})^2)"
            )
            right_curve = (
                f"Height/2{sign}Height/2*SQRT(1-(({position}-(Width-{radius}))/"
                f"{radius})^2)"
            )
            edge = "Height" if port.side == "top" else "0"
            x_formula = position
            y_formula = (
                f"IF({position}<{radius},{left_curve},"
                f"IF({position}>Width-{radius},{right_curve},{edge}))"
            )
    elif plan.master_marker == "__template_input_output__":
        slant = "MIN(Height/4,Width/4)"
        if port.side in {"left", "right"}:
            shift = f"{slant}*{1.0 - 2.0 * offset:.15g}"
            x_formula = shift if port.side == "left" else f"Width+{shift}"
            y_formula = f"Height*{1.0 - offset:.15g}"
        else:
            position = f"Width*{offset:.15g}"
            x_formula = position
            if port.side == "top":
                y_formula = (
                    f"IF({position}<{slant},"
                    f"Height*({position}+{slant})/(2*{slant}),Height)"
                )
            else:
                y_formula = (
                    f"IF({position}>Width-{slant},"
                    f"Height*({position}-(Width-{slant}))/(2*{slant}),0)"
                )
    elif plan.master_marker == "__template_delay__":
        sagitta = "MIN(Width,Height)/2"
        radius = f"((Height/2)^2+({sagitta})^2)/(2*({sagitta}))"
        center = f"Width-({radius})"
        if port.side == "right":
            local_y = f"Height*{1.0 - offset:.15g}"
            x_formula = (
                f"({center})+SQRT(({radius})^2-({local_y}-Height/2)^2)"
            )
            y_formula = local_y
        elif port.side in {"top", "bottom"}:
            position = f"Width*{offset:.15g}"
            sign = "+" if port.side == "top" else "-"
            curve = (
                f"Height/2{sign}SQRT(({radius})^2-({position}-({center}))^2)"
            )
            edge = "Height" if port.side == "top" else "0"
            x_formula = position
            y_formula = f"IF({position}>Width-({sagitta}),{curve},{edge})"
    elif plan.master_marker in {"__template_controller__", "__template_interface__"}:
        radius = "MIN(Width*0.1,Width/2,Height/2)"
        if port.side in {"left", "right"}:
            local_y = f"Height*{1.0 - offset:.15g}"
            bottom_inset = (
                f"{radius}-SQRT(({radius})^2-({local_y}-{radius})^2)"
            )
            top_inset = (
                f"{radius}-SQRT(({radius})^2-"
                f"({local_y}-(Height-{radius}))^2)"
            )
            inset = (
                f"IF({local_y}<{radius},{bottom_inset},"
                f"IF({local_y}>Height-{radius},{top_inset},0))"
            )
            x_formula = inset if port.side == "left" else f"Width-({inset})"
            y_formula = local_y
        else:
            local_x = f"Width*{offset:.15g}"
            left_inset = f"{radius}-SQRT(({radius})^2-({local_x}-{radius})^2)"
            right_inset = (
                f"{radius}-SQRT(({radius})^2-"
                f"({local_x}-(Width-{radius}))^2)"
            )
            inset = (
                f"IF({local_x}<{radius},{left_inset},"
                f"IF({local_x}>Width-{radius},{right_inset},0))"
            )
            x_formula = local_x
            y_formula = (
                f"Height-({inset})" if port.side == "top" else inset
            )
    elif plan.master_marker == "__template_database__":
        sagitta = "MIN(Height/8,Width/8)"
        radius = f"((Height/2)^2+({sagitta})^2)/(2*({sagitta}))"
        if port.side in {"left", "right"}:
            local_y = f"Height*{1.0 - offset:.15g}"
            curve = f"SQRT(({radius})^2-({local_y}-Height/2)^2)"
            if port.side == "left":
                x_formula = f"({radius})-({curve})"
            else:
                x_formula = f"Width+({sagitta})-({radius})+({curve})"
            y_formula = local_y
        else:
            position = f"Width*{offset:.15g}"
            sign = "+" if port.side == "top" else "-"
            left_curve = (
                f"Height/2{sign}SQRT(({radius})^2-({position}-({radius}))^2)"
            )
            edge = "Height" if port.side == "top" else "0"
            x_formula = position
            y_formula = f"IF({position}<({sagitta}),{left_curve},{edge})"
    elif plan.master_marker == "__template_document__":
        wave = "MIN(MIN(Width,Height)/8,Width/12)"
        radius = f"((Width/4)^2+({wave})^2)/(2*({wave}))"
        if port.side == "bottom":
            position = f"Width*{offset:.15g}"
            left_wave = (
                f"({radius})-SQRT(({radius})^2-({position}-Width/4)^2)"
            )
            right_wave = (
                f"2*({wave})-({radius})+"
                f"SQRT(({radius})^2-({position}-3*Width/4)^2)"
            )
            x_formula = position
            y_formula = (
                f"IF({position}<=Width/2,{left_wave},{right_wave})"
            )
        elif port.side in {"left", "right"}:
            local_y = f"Height*{1.0 - offset:.15g}"
            curve = f"SQRT(({radius})^2-({local_y}-({radius}))^2)"
            wave_x = (
                f"Width/4+({curve})"
                if port.side == "right"
                else f"Width/4-({curve})"
            )
            x_formula = f"IF({local_y}<({wave}),{wave_x},{'Width' if port.side == 'right' else '0'})"
            y_formula = local_y
    elif plan.master_marker == "__template_note__":
        fold_x = "User.XFoldLength"
        fold_y = "User.YFoldLength"
        if port.side == "right":
            local_y = f"Height*{1.0 - offset:.15g}"
            x_formula = (
                f"IF({local_y}<{fold_y},Width-{fold_x}+"
                f"{fold_x}*{local_y}/{fold_y},Width)"
            )
            y_formula = local_y
        elif port.side == "bottom":
            local_x = f"Width*{offset:.15g}"
            x_formula = local_x
            y_formula = (
                f"IF({local_x}>Width-{fold_x},{fold_y}*"
                f"({local_x}-(Width-{fold_x}))/{fold_x},0)"
            )
    return x_formula, y_formula


def _configure_container_header(label_shape: Shape, plan: IRShape) -> None:
    if plan.container is None:
        return
    width = plan.rect.width - 2 * plan.container.padding
    height = plan.container.header_height
    child_shapes = label_shape.xml.find(f"{namespace}Shapes")
    if child_shapes is not None:
        for child in label_shape.child_shapes:
            _hide_shape_tree(child)
    _replace_rectangle_geometry(label_shape, width, height)
    for name, value in (
        ("PinX", plan.rect.width / 2),
        ("PinY", plan.rect.height - height / 2),
        ("Width", width),
        ("Height", height),
        ("LocPinX", width / 2),
        ("LocPinY", height / 2),
        ("TxtPinX", width / 2),
        ("TxtPinY", height / 2),
        ("TxtLocPinX", width / 2),
        ("TxtLocPinY", height / 2),
    ):
        _set_local_cell_value(label_shape, name, f"{value:.15g}")
    _set_local_cell_value(label_shape, "TxtWidth", f"{width:.15g}")
    _set_local_cell_value(label_shape, "TxtHeight", f"{height:.15g}")
    # Container typography is commonly light, so give the explicit header a
    # deterministic high-contrast fill instead of inheriting a transparent
    # palette child.
    _set_local_cell_value(label_shape, "FillForegnd", plan.style.line_color)
    _set_local_cell_value(label_shape, "FillPattern", "1")
    _set_local_cell_value(label_shape, "LineColor", plan.style.line_color)
    _set_local_cell_value(label_shape, "LinePattern", "1")
    _set_section_cell(
        label_shape,
        "Character",
        {"IX": "0"},
        "Color",
        _contrasting_text_color(plan.style.line_color),
    )


def _add_ir_connection(
    page: Page,
    connector: Shape,
    endpoint: str,
    target: Shape,
    port_name: str,
) -> None:
    if port_name == "dynamic":
        to_cell = "PinX"
        to_part = "3"
    else:
        to_cell = f"Connections.{port_name}"
        connection_section = target.xml.find(
            f"{namespace}Section[@N='Connection']"
        )
        if connection_section is None:
            raise RenderingError(
                f"shape {target.ID} has no connection points for port {port_name!r}"
            )
        active_rows = [
            row
            for row in connection_section.findall(f"{namespace}Row")
            if row.attrib.get("Del") != "1"
        ]
        local_row_index = next(
            (
                index
                for index, row in enumerate(active_rows)
                if row.attrib.get("N") == port_name
            ),
            None,
        )
        if local_row_index is None:
            raise RenderingError(
                f"shape {target.ID} has no connection point named {port_name!r}"
            )
        inherited_rows = []
        if target.master_shape is not None:
            master_section = target.master_shape.xml.find(
                f"{namespace}Section[@N='Connection']"
            )
            if master_section is not None:
                inherited_rows = [
                    row
                    for row in master_section.findall(f"{namespace}Row")
                    if row.attrib.get("Del") != "1"
                ]
        row_index = len(inherited_rows) + local_row_index
        # Visio's ToPart value is 100 plus the zero-based Connection-row index.
        # Master rows remain inherited and precede newly added named rows, so the
        # effective index includes both sets.  It must agree with ToCell;
        # hard-coded side indexes corrupt ports such as flow_in/flow_out when
        # Visio recalculates after a move.
        to_part = str(100 + row_index)
    attributes = {
        "FromSheet": connector.ID,
        "FromCell": endpoint,
        "FromPart": "9" if endpoint == "BeginX" else "12",
        "ToSheet": target.ID,
        "ToCell": to_cell,
        "ToPart": to_part,
    }
    page.add_connect(
        Connect(xml=ET.Element(f"{namespace}Connect", attributes), page=page)
    )


def _replace_route_geometry(
    connector: Shape,
    route: tuple[IRPoint, ...],
    page_height: float,
    connector_type: str,
) -> None:
    points = tuple(_to_visio_point(page_height, point) for point in route)
    minimum_x = min(point[0] for point in points)
    minimum_y = min(point[1] for point in points)
    maximum_x = max(point[0] for point in points)
    maximum_y = max(point[1] for point in points)
    width = max(maximum_x - minimum_x, 0.25)
    height = max(maximum_y - minimum_y, 0.25)
    intermediate = points[1:-1]
    for axis, minimum, maximum, dimension in (
        ("X", minimum_x, maximum_x, width),
        ("Y", minimum_y, maximum_y, height),
    ):
        fixed = [f"{point[0 if axis == 'X' else 1]:.15g}" for point in intermediate]
        arguments = ",".join((f"Begin{axis}", f"End{axis}", *fixed))
        low = f"MIN({arguments})"
        high = f"MAX({arguments})"
        dimension_name = "Width" if axis == "X" else "Height"
        _set_local_cell_formula(
            connector,
            f"Pin{axis}",
            f"{(minimum + maximum) / 2:.15g}",
            f"GUARD(({low}+{high})/2)",
        )
        _set_local_cell_formula(
            connector,
            dimension_name,
            f"{dimension:.15g}",
            f"GUARD(MAX({high}-{low},0.25DL))",
        )
        _set_local_cell_formula(
            connector,
            f"LocPin{axis}",
            f"{dimension / 2:.15g}",
            f"GUARD({dimension_name}/2)",
        )
    for section in connector.xml.findall(f"{namespace}Section[@N='Geometry']"):
        connector.xml.remove(section)
    geometry = ET.SubElement(
        connector.xml, f"{namespace}Section", {"N": "Geometry", "IX": "0"}
    )
    for index, (x, y) in enumerate(points, start=1):
        row = ET.SubElement(
            geometry,
            f"{namespace}Row",
            {"T": "MoveTo" if index == 1 else "LineTo", "IX": str(index)},
        )
        x_cell = ET.SubElement(
            row, f"{namespace}Cell", {"N": "X", "V": f"{x - minimum_x:.15g}"}
        )
        y_cell = ET.SubElement(
            row, f"{namespace}Cell", {"N": "Y", "V": f"{y - minimum_y:.15g}"}
        )
        if index == 1:
            x_cell.attrib["F"] = "BeginX-PinX+LocPinX"
            y_cell.attrib["F"] = "BeginY-PinY+LocPinY"
        elif index == len(points):
            x_cell.attrib["F"] = "EndX-PinX+LocPinX"
            y_cell.attrib["F"] = "EndY-PinY+LocPinY"
        else:
            x_cell.attrib["F"] = f"{x:.15g}-PinX+LocPinX"
            y_cell.attrib["F"] = f"{y:.15g}-PinY+LocPinY"
            if connector_type == "orthogonal" and index == 2:
                previous_x, previous_y = points[0]
                if math.isclose(y, previous_y, abs_tol=1e-12):
                    y_cell.attrib["F"] = "BeginY-PinY+LocPinY"
                elif math.isclose(x, previous_x, abs_tol=1e-12):
                    x_cell.attrib["F"] = "BeginX-PinX+LocPinX"
            if connector_type == "orthogonal" and index == len(points) - 1:
                following_x, following_y = points[-1]
                if math.isclose(y, following_y, abs_tol=1e-12):
                    y_cell.attrib["F"] = "EndY-PinY+LocPinY"
                elif math.isclose(x, following_x, abs_tol=1e-12):
                    x_cell.attrib["F"] = "EndX-PinX+LocPinX"
    _delete_unused_master_geometry_rows(connector, set(range(1, len(points) + 1)))


def _style_ir_connector(connector: Shape, plan: IRConnector) -> None:
    _set_local_cell_value(
        connector,
        "BeginArrow",
        _ARROW_STYLE if plan.arrowheads in {"begin", "both"} else "0",
    )
    _set_local_cell_value(
        connector,
        "EndArrow",
        _ARROW_STYLE if plan.arrowheads in {"end", "both"} else "0",
    )
    _set_local_cell_value(
        connector, "LinePattern", _LINE_PATTERNS[plan.style.line_pattern]
    )
    _set_local_cell_value(
        connector, "LineWeight", f"{plan.style.line_weight_pt / 72:.15g}"
    )
    _set_local_cell_value(connector, "LineColor", plan.style.line_color)
    _set_local_cell_value(connector, "ConLineJumpCode", "1" if plan.jumps else "0")


def _configure_connector_label(
    connector: Shape, plan: IRConnector, page_height: float
) -> None:
    if plan.label is None:
        return
    pin_x = float(connector.cell_value("PinX"))
    pin_y = float(connector.cell_value("PinY"))
    loc_pin_x = float(connector.cell_value("LocPinX"))
    loc_pin_y = float(connector.cell_value("LocPinY"))
    label_x = plan.label.position.x
    label_y = page_height - plan.label.position.y + plan.label.offset
    _set_local_cell_value(connector, "TxtPinX", f"{label_x - pin_x + loc_pin_x:.15g}")
    _set_local_cell_value(connector, "TxtPinY", f"{label_y - pin_y + loc_pin_y:.15g}")
    if plan.label.orientation == "along_route":
        start, end = plan.route[0], plan.route[-1]
        angle = math.atan2(start.y - end.y, end.x - start.x)
        _set_local_cell_value(connector, "TxtAngle", f"{angle:.15g}")
    _set_local_cell_value(connector, "HideText", "0")
    _set_local_cell_value(
        connector,
        "TextBkgnd",
        "#FFFFFF" if plan.label.background == "opaque" else "0",
    )


def _configure_ir_callout(
    callout: Shape,
    plan: IRCallout,
    target: Shape,
    page_height: float,
) -> None:
    x = plan.rect.x + plan.rect.width / 2
    y = page_height - plan.rect.y - plan.rect.height / 2
    for name, value in (
        ("PinX", x),
        ("PinY", y),
        ("Width", plan.rect.width),
        ("Height", plan.rect.height),
        ("LocPinX", plan.rect.width / 2),
        ("LocPinY", plan.rect.height / 2),
    ):
        _set_local_cell_value(callout, name, f"{value:.15g}")
    for name, value in (
        ("TxtPinX", plan.rect.width / 2),
        ("TxtPinY", plan.rect.height / 2),
        ("TxtWidth", plan.rect.width),
        ("TxtHeight", plan.rect.height),
        ("TxtLocPinX", plan.rect.width / 2),
        ("TxtLocPinY", plan.rect.height / 2),
        ("VerticalAlign", 1),
    ):
        _set_local_cell_value(callout, name, f"{value:.15g}")
    _set_section_cell(callout, "Paragraph", {"IX": "0"}, "HorzAlign", "1")
    _set_local_cell_formula(
        callout,
        "Relationships",
        "0",
        f"SUM(DEPENDSON(6,Sheet.{target.ID}!SheetRef()))",
    )
    route = tuple(_to_visio_point(page_height, point) for point in plan.leader_route)
    for section in callout.xml.findall(f"{namespace}Section[@N='Geometry'][@IX='0']"):
        callout.xml.remove(section)
    geometry = ET.Element(f"{namespace}Section", {"N": "Geometry", "IX": "0"})
    body = callout.xml.find(f"{namespace}Section[@N='Geometry']")
    insert_at = list(callout.xml).index(body) if body is not None else len(callout.xml)
    callout.xml.insert(insert_at, geometry)
    owner_left = plan.rect.x
    owner_bottom = page_height - plan.rect.y - plan.rect.height
    for index, (point_x, point_y) in enumerate(route, start=1):
        row = ET.SubElement(
            geometry,
            f"{namespace}Row",
            {"T": "MoveTo" if index == 1 else "LineTo", "IX": str(index)},
        )
        ET.SubElement(
            row, f"{namespace}Cell", {"N": "X", "V": f"{point_x - owner_left:.15g}"}
        )
        ET.SubElement(
            row, f"{namespace}Cell", {"N": "Y", "V": f"{point_y - owner_bottom:.15g}"}
        )
        if index == len(route):
            row.find(f"{namespace}Cell[@N='X']").attrib["F"] = (
                f"Sheet.{target.ID}!PinX-PinX+LocPinX"
            )
            row.find(f"{namespace}Cell[@N='Y']").attrib["F"] = (
                f"Sheet.{target.ID}!PinY-PinY+LocPinY"
            )
    _delete_unused_master_geometry_rows(callout, set(range(1, len(route) + 1)))


def _add_relationship(shape: Shape, relationship: int, targets: list[Shape]) -> None:
    if not targets:
        return
    dependency = "DEPENDSON(" + str(relationship) + "," + ",".join(
        f"Sheet.{target.ID}!SheetRef()" for target in targets
    ) + ")"
    existing = shape.cell_formula("Relationships")
    if existing and existing.startswith("SUM(") and existing.endswith(")"):
        dependency = existing[4:-1] + "," + dependency
    _set_local_cell_formula(shape, "Relationships", "0", f"SUM({dependency})")


def _apply_container_membership(container: Shape, members: list[Shape]) -> None:
    _set_section_cell(
        container, "User", {"N": "msvStructureType"}, "Value", "Container"
    )
    _set_section_cell(container, "User", {"N": "msvSDContainerResize"}, "Value", "0")
    _set_local_cell_value(container, "DontMoveChildren", "1")
    _block_master_inheritance(container, ("DontMoveChildren",))
    _add_relationship(container, 1, members)
    for member in members:
        _add_relationship(member, 4, [container])


def _reorder_ir_shapes(page: Page, order: list[tuple[int, int, Shape]]) -> None:
    shapes_element = page.xml.find(f"{namespace}Shapes")
    if shapes_element is None:
        raise RenderingError("output page has no Shapes element")
    for _, _, shape in order:
        shapes_element.remove(shape.xml)
    for _, _, shape in sorted(order, key=lambda item: (item[0], item[1])):
        shapes_element.append(shape.xml)


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
    _require_distinct_output(source, destination)
    if not all(
        math.isfinite(value) for value in (layout.page.width, layout.page.height)
    ):
        raise RenderingError("finite page geometry required")
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
            tolerance = 1e-6
            if (
                x - width / 2 < -tolerance
                or x + width / 2 > layout.page.width + tolerance
                or y - height / 2 < -tolerance
                or y + height / 2 > layout.page.height + tolerance
            ):
                raise RenderingError(f"node '{node.id}' lies outside the layout page")
            visual = map_node_visual(
                node.type,
                available_markers=palette.shapes.keys(),
            )
            copied_shape = _copy_shape_tree(
                palette.shapes[visual.marker].shape,
                palette.page,
            )
            _find_marker_shape(copied_shape, visual.marker).text = node.label
            _set_local_cell_value(copied_shape, "Width", f"{width:.15g}")
            _set_local_cell_value(copied_shape, "Height", f"{height:.15g}")
            _set_local_cell_value(copied_shape, "PinX", f"{x:.15g}")
            _set_local_cell_value(copied_shape, "PinY", f"{y:.15g}")
            node_shapes[node.id] = copied_shape

        callout_marker = "__template_reference_callout__"
        component_marker = "__template_component_rectangle__"
        used_reference_numbers = {
            node.reference_number
            for node in layout.graph.nodes
            if node.reference_number is not None
        }
        next_automatic_reference = 1
        for node in layout.graph.nodes:
            reference_number = node.reference_number
            if reference_number is None and automatic_reference_numbers:
                while str(next_automatic_reference) in used_reference_numbers:
                    next_automatic_reference += 1
                reference_number = str(next_automatic_reference)
                used_reference_numbers.add(reference_number)
                next_automatic_reference += 1
            if reference_number is None:
                continue
            target = node_shapes[node.id]
            callout = _copy_shape_tree(
                palette.shapes[callout_marker].shape,
                palette.page,
            )
            if callout.width > layout.page.width or callout.height > layout.page.height:
                raise RenderingError(
                    f"reference callout for node '{node.id}' cannot fit inside the layout page"
                )
            _find_marker_shape(callout, callout_marker).text = reference_number
            _place_reference_callout(
                callout,
                target,
                layout.page.width,
                layout.page.height,
            )
            _retarget_sheet_references(
                callout,
                {palette.shapes[component_marker].shape.ID: target.ID},
            )
            _attach_callout_leader(callout, target)

        connector_marker = "__template_connector__"
        process_marker = "__template_process__"
        nodes_by_id = {node.id: node for node in layout.graph.nodes}
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
                line_style=edge.style if "style" in edge.model_fields_set else None,
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
            start, finish = _boundary_points(
                nodes_by_id[edge.source],
                nodes_by_id[edge.target],
            )
            _set_connector_cached_geometry(connector, start, finish)
            _configure_dynamic_connector_glue(
                connector,
                source_shape,
                target_shape,
                start,
                finish,
            )
            _style_connector(connector, visual)

        palette.page.width = layout.page.width
        palette.page.height = layout.page.height
        _remove_template_palette(palette)
        _save_vsdx(palette.document, destination)

    return destination


def render_ir(
    template_path: str | Path,
    ir: RendererIR,
    output_path: str | Path,
) -> Path:
    """Render a validated Generation v2 IR with explicit native Visio geometry."""

    source = Path(template_path)
    destination = Path(output_path)
    _require_distinct_output(source, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with load_template_palette(source, markers=PRODUCTION_TEMPLATE_MARKERS) as palette:
        rendered_shapes: dict[str, Shape] = {}
        shapes_by_object: dict[str, Shape] = {}
        render_order: list[tuple[int, int, Shape]] = []
        sequence = 0
        for plan in ir.shapes:
            copied = _copy_shape_tree(
                palette.shapes[plan.master_marker].shape,
                palette.page,
            )
            _strip_inherited_dimension_caches(copied)
            label = _find_marker_shape(copied, plan.master_marker)
            label.text = plan.container.header_text if plan.container else plan.text
            x, y, width, height = _shape_geometry(ir.page.height, plan)
            _resize_group_children(copied, width, height)
            if plan.container:
                _replace_container_body(copied, label, width, height)
            for name, value in (
                ("PinX", x),
                ("PinY", y),
                ("Width", width),
                ("Height", height),
                ("LocPinX", width / 2),
                ("LocPinY", height / 2),
            ):
                _set_local_cell_value(copied, name, f"{value:.15g}")
            _set_local_cell_value(copied, "Relationships", "0")
            _style_ir_shape(copied, plan)
            _configure_ir_text(label, plan, ir.page.height)
            _configure_container_header(label, plan)
            _block_master_inheritance(
                copied,
                (
                    "PinX", "PinY", "Width", "Height", "LocPinX", "LocPinY",
                    "FillForegnd", "LineColor", "LineWeight", "LinePattern",
                ),
            )
            _block_master_inheritance(
                label,
                (
                    "PinX", "PinY", "Width", "Height", "LocPinX", "LocPinY",
                    "TxtPinX", "TxtPinY", "TxtLocPinX", "TxtLocPinY",
                    "TxtWidth", "TxtHeight", "VerticalAlign",
                ),
            )
            _stabilize_transform_tree(copied)
            _replace_connection_points(copied, plan, ir.page.height)
            if plan.container:
                _set_section_cell(
                    copied,
                    "User",
                    {"N": "msvSDContainerMargin"},
                    "Value",
                    f"{plan.container.padding:.15g}",
                )
            rendered_shapes[plan.id] = copied
            shapes_by_object[plan.object_id] = copied
            render_order.append((plan.z_order, sequence, copied))
            sequence += 1

        for plan in ir.shapes:
            if plan.container is None:
                continue
            _apply_container_membership(
                rendered_shapes[plan.id],
                [
                    shapes_by_object[member_id]
                    for member_id in plan.container.member_ids
                ],
            )

        for plan in ir.connectors:
            source_shape = rendered_shapes[plan.source_shape_id]
            target_shape = rendered_shapes[plan.target_shape_id]
            connector = _copy_shape_tree(
                palette.shapes[plan.master_marker].shape,
                palette.page,
            )
            _strip_inherited_dimension_caches(connector)
            _find_marker_shape(connector, plan.master_marker).text = (
                plan.label.text if plan.label else ""
            )
            start = _to_visio_point(ir.page.height, plan.route[0])
            finish = _to_visio_point(ir.page.height, plan.route[-1])
            _set_connector_cached_geometry(connector, start, finish)
            if plan.connector_type == "dynamic":
                _configure_dynamic_connector_glue(
                    connector, source_shape, target_shape, start, finish
                )
            else:
                _configure_explicit_connector_glue(
                    connector,
                    source_shape,
                    plan.source_port,
                    target_shape,
                    plan.target_port,
                    start,
                    finish,
                )
                _replace_route_geometry(
                    connector,
                    plan.route,
                    ir.page.height,
                    plan.connector_type,
                )
                _set_local_cell_value(
                    connector,
                    "ShapeRouteStyle",
                    "1" if plan.connector_type == "orthogonal" else "2",
                )
                _set_local_cell_value(
                    connector,
                    "ConLineRouteExt",
                    "1" if plan.connector_type == "straight" else "0",
                )
                _block_master_inheritance(
                    connector, ("ShapeRouteStyle", "ConLineRouteExt")
                )
            _add_ir_connection(
                palette.page,
                connector,
                "BeginX",
                source_shape,
                plan.source_port,
            )
            _add_ir_connection(
                palette.page,
                connector,
                "EndX",
                target_shape,
                plan.target_port,
            )
            _style_ir_connector(connector, plan)
            _configure_connector_label(connector, plan, ir.page.height)
            _block_master_inheritance(
                connector,
                (
                    "BeginArrow", "EndArrow", "LinePattern", "LineWeight",
                    "LineColor", "ConLineJumpCode",
                ),
            )
            if plan.label is not None:
                label_cells = ["TxtPinX", "TxtPinY", "HideText", "TextBkgnd"]
                if plan.label.orientation == "along_route":
                    label_cells.append("TxtAngle")
                _block_master_inheritance(connector, label_cells)
            render_order.append((plan.z_order, sequence, connector))
            sequence += 1

        for plan in ir.callouts:
            callout = _copy_shape_tree(
                palette.shapes[plan.master_marker].shape,
                palette.page,
            )
            _strip_inherited_dimension_caches(callout)
            _find_marker_shape(callout, plan.master_marker).text = plan.text
            _configure_ir_callout(
                callout, plan, shapes_by_object[plan.object_id], ir.page.height
            )
            _block_master_inheritance(
                callout,
                (
                    "PinX", "PinY", "Width", "Height", "LocPinX", "LocPinY",
                    "TxtPinX", "TxtPinY", "TxtWidth", "TxtHeight", "VerticalAlign",
                    "TxtLocPinX", "TxtLocPinY",
                ),
            )
            _stabilize_transform_tree(callout)
            render_order.append((plan.z_order, sequence, callout))
            sequence += 1

        palette.page.width = ir.page.width
        palette.page.height = ir.page.height
        _remove_template_palette(palette)
        _reorder_ir_shapes(palette.page, render_order)
        _save_vsdx(palette.document, destination)

    return destination


def render_feasibility_spike(
    template_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Copy and relabel all five palette objects into a generated VSDX artifact."""

    source = Path(template_path)
    destination = Path(output_path)
    _require_distinct_output(source, destination)
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
        start, finish = _boundary_points(
            copies[process_marker],
            copies[component_marker],
        )
        _set_connector_cached_geometry(copied_connector, start, finish)
        _configure_dynamic_connector_glue(
            copied_connector,
            copies[process_marker],
            copies[component_marker],
            start,
            finish,
        )

        _remove_template_palette(palette)
        _save_vsdx(palette.document, destination)

    return destination
