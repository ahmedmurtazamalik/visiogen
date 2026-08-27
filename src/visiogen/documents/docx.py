"""Portable, non-rendering DOCX text and embedded-media extraction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from visiogen.documents.errors import (
    DocumentExtractionError,
    UnsafeDocumentError,
)
from visiogen.documents.image import inspect_raster_dimensions
from visiogen.documents.models import (
    CoverageReport,
    DocumentSnapshot,
    ExtractionWarning,
    SourceLocation,
    TextBlock,
    VisualAsset,
)
from visiogen.documents.safety import DocumentSafetyLimits
from visiogen.documents.sniffing import AdmittedDocument

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PR = "http://schemas.openxmlformats.org/package/2006/relationships"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
}


def _parse_xml(data: bytes, name: str) -> ET.Element:
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise UnsafeDocumentError(f"DOCX XML declarations are unsafe: {name}")
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise DocumentExtractionError(f"DOCX XML is malformed: {name}") from error


def _relationships(
    archive: ZipFile,
    name: str,
    *,
    relationship_type: str | None = None,
) -> dict[str, str]:
    if name not in archive.namelist():
        return {}
    root = _parse_xml(archive.read(name), name)
    relationships: dict[str, str] = {}
    for relation in root.findall(f"{{{_PR}}}Relationship"):
        relation_id = relation.get("Id")
        target = relation.get("Target")
        if relation.get("TargetMode", "Internal").lower() == "external":
            raise UnsafeDocumentError(f"External DOCX relationship is not supported: {name}")
        if relationship_type is not None and relation.get("Type") != relationship_type:
            continue
        if relation_id and target:
            relationships[relation_id] = target
    return relationships


def _resolved_word_target(target: str) -> str:
    normalized = posixpath.normpath(posixpath.join("word", target))
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or not normalized.startswith("word/"):
        raise UnsafeDocumentError(f"DOCX relationship escapes the Word package: {target}")
    return normalized


def _paragraph_text(paragraph: ET.Element) -> str:
    pieces: list[str] = []
    for element in paragraph.iter():
        if element.tag == f"{{{_W}}}t" and element.text:
            pieces.append(element.text)
        elif element.tag == f"{{{_W}}}tab":
            pieces.append("\t")
        elif element.tag in {f"{{{_W}}}br", f"{{{_W}}}cr"}:
            pieces.append("\n")
    return "".join(pieces).strip()


def _paragraph_style(paragraph: ET.Element) -> str | None:
    style = paragraph.find(f"./{{{_W}}}pPr/{{{_W}}}pStyle")
    if style is None:
        return None
    return style.get(f"{{{_W}}}val")


def _paragraph_origin(part_name: str, style_name: str | None) -> str:
    if part_name.startswith("word/header"):
        return "header"
    if part_name.startswith("word/footer"):
        return "footer"
    if part_name == "word/footnotes.xml":
        return "footnote"
    if part_name == "word/endnotes.xml":
        return "endnote"
    if (style_name or "").lower() == "caption":
        return "caption"
    return "native"


def _image_relationship_ids(paragraph: ET.Element) -> list[str]:
    ids: list[str] = []
    for blip in paragraph.iter(f"{{{_A}}}blip"):
        relation_id = blip.get(f"{{{_R}}}embed")
        if relation_id and relation_id not in ids:
            ids.append(relation_id)
    return ids


def _alt_texts(paragraph: ET.Element) -> list[str]:
    values: list[str] = []
    for properties in paragraph.iter(f"{{{_WP}}}docPr"):
        for key in ("descr", "title"):
            value = (properties.get(key) or "").strip()
            if value and value not in values:
                values.append(value)
    return values


def extract_docx_snapshot(
    admitted: AdmittedDocument,
    stage: Path,
    *,
    limits: DocumentSafetyLimits,
) -> DocumentSnapshot:
    """Extract native text and bounded embedded raster media from an admitted DOCX."""

    assets_dir = stage / "assets"
    assets_dir.mkdir()
    with ZipFile(admitted.path) as archive:
        for rels_name in sorted(name for name in archive.namelist() if name.endswith(".rels")):
            _relationships(archive, rels_name)
        if any(name.startswith("word/embeddings/") for name in archive.namelist()):
            raise UnsafeDocumentError("Embedded OLE/package content is not supported")

        document_root = _parse_xml(archive.read("word/document.xml"), "word/document.xml")
        if any(element.tag == f"{{{_W}}}object" for element in document_root.iter()):
            raise UnsafeDocumentError("Embedded Word objects are not supported")
        document_relationships = _relationships(
            archive,
            "word/_rels/document.xml.rels",
            relationship_type=_REL_IMAGE,
        )
        relation_targets = {
            relation_id: _resolved_word_target(target)
            for relation_id, target in document_relationships.items()
        }
        image_relations = {
            relation_id: target
            for relation_id, target in relation_targets.items()
            if target.startswith("word/media/")
        }
        reverse_relations = {target: relation_id for relation_id, target in image_relations.items()}

        visual_assets: list[VisualAsset] = []
        asset_by_relation: dict[str, str] = {}
        warnings: list[ExtractionWarning] = []
        media_names = sorted(name for name in archive.namelist() if name.startswith("word/media/"))
        for index, member_name in enumerate(media_names, start=1):
            suffix = Path(member_name).suffix.lower()
            media_type = _MEDIA_TYPES.get(suffix)
            relation_id = reverse_relations.get(member_name)
            if media_type is None:
                warnings.append(
                    ExtractionWarning(
                        code="unsupported_embedded_media",
                        message=f"Embedded media format was not extracted: {member_name}",
                        location=SourceLocation(relationship_id=relation_id),
                    )
                )
                continue
            data = archive.read(member_name)
            dimensions = inspect_raster_dimensions(data, limits=limits)
            asset_id = f"asset-{len(visual_assets) + 1:04d}"
            filename = f"{asset_id}{suffix}"
            (assets_dir / filename).write_bytes(data)
            visual_assets.append(
                VisualAsset(
                    id=asset_id,
                    media_type=media_type,
                    origin="embedded",
                    sha256=hashlib.sha256(data).hexdigest(),
                    byte_size=len(data),
                    artifact_path=f"assets/{filename}",
                    width_px=dimensions.width,
                    height_px=dimensions.height,
                    location=SourceLocation(relationship_id=relation_id),
                )
            )
            if relation_id:
                asset_by_relation[relation_id] = asset_id

        text_blocks: list[TextBlock] = []
        ancillary_names = sorted(
            name
            for name in archive.namelist()
            if (
                name.startswith("word/header")
                or name.startswith("word/footer")
                or name in {"word/footnotes.xml", "word/endnotes.xml"}
            )
            and name.endswith(".xml")
        )
        parts = [("word/document.xml", document_root)]
        parts.extend((name, _parse_xml(archive.read(name), name)) for name in ancillary_names)
        for part_name, part_root in parts:
            for paragraph_index, paragraph in enumerate(part_root.iter(f"{{{_W}}}p")):
                text = _paragraph_text(paragraph)
                relation_ids = _image_relationship_ids(paragraph)
                style_name = _paragraph_style(paragraph)
                if text:
                    block_id = f"text-{len(text_blocks) + 1:04d}"
                    text_blocks.append(
                        TextBlock(
                            id=block_id,
                            text=text,
                            origin=_paragraph_origin(part_name, style_name),
                            style_name=style_name,
                            order=len(text_blocks),
                            location=SourceLocation(
                                part_name=part_name,
                                block_id=block_id,
                                paragraph_index=paragraph_index,
                                relationship_id=relation_ids[0] if relation_ids else None,
                                asset_id=(
                                    asset_by_relation.get(relation_ids[0])
                                    if relation_ids
                                    else None
                                ),
                            ),
                        )
                    )
                for alt_text in _alt_texts(paragraph):
                    relation_id = relation_ids[0] if relation_ids else None
                    block_id = f"text-{len(text_blocks) + 1:04d}"
                    text_blocks.append(
                        TextBlock(
                            id=block_id,
                            text=alt_text,
                            origin="alt_text",
                            order=len(text_blocks),
                            location=SourceLocation(
                                part_name=part_name,
                                block_id=block_id,
                                paragraph_index=paragraph_index,
                                relationship_id=relation_id,
                                asset_id=(
                                    asset_by_relation.get(relation_id) if relation_id else None
                                ),
                            ),
                        )
                    )

        drawing_count = sum(1 for _ in document_root.iter(f"{{{_W}}}drawing"))
        if drawing_count:
            warnings.append(
                ExtractionWarning(
                    code="word_drawings_not_rendered",
                    message=(
                        "Portable DOCX mode extracted embedded media but did not render "
                        "Word drawing layout, shapes, SmartArt, charts, or text boxes"
                    ),
                )
            )

    snapshot = DocumentSnapshot(
        source_id=f"sha256:{admitted.sha256}",
        source_sha256=admitted.sha256,
        source_name=admitted.path.name,
        document_kind="docx",
        media_type=admitted.media_type,
        byte_size=admitted.byte_size,
        page_count=None,
        text_blocks=text_blocks,
        visual_assets=visual_assets,
        warnings=warnings,
        coverage=CoverageReport(
            native_text="complete",
            embedded_media="complete",
            rendered_pages="not_available",
            word_drawings="not_available",
        ),
    )
    (stage / "snapshot.json").write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return snapshot
