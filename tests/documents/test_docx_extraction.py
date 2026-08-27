"""Tests for portable DOCX text, relationship, and media extraction."""

import json
from pathlib import Path

import pytest

from fixture_builders import write_diagram_docx
from visiogen.documents.errors import UnsafeDocumentError
from visiogen.documents.extractor import extract_document


def test_extract_docx_writes_complete_portable_snapshot_bundle(tmp_path: Path) -> None:
    source = write_diagram_docx(tmp_path / "diagram.docx")
    output = tmp_path / "evidence"

    snapshot = extract_document(source, output)

    assert snapshot.document_kind == "docx"
    assert snapshot.page_count is None
    assert [block.text for block in snapshot.text_blocks] == [
        "System overview",
        "Processor",
        "Controller",
        "Sensor diagram",
        "Figure 1",
        "Confidential",
    ]
    assert [block.origin for block in snapshot.text_blocks] == [
        "native",
        "native",
        "native",
        "alt_text",
        "caption",
        "header",
    ]
    assert snapshot.text_blocks[0].style_name == "Heading1"
    assert len(snapshot.visual_assets) == 1
    asset = snapshot.visual_assets[0]
    assert (asset.width_px, asset.height_px) == (1, 1)
    assert asset.location.relationship_id == "rId1"
    assert snapshot.text_blocks[3].location.asset_id == asset.id
    assert (output / asset.artifact_path).read_bytes().startswith(b"\x89PNG")
    persisted = json.loads((output / "snapshot.json").read_text())
    assert persisted == snapshot.model_dump(mode="json")
    assert snapshot.coverage.rendered_pages == "not_available"
    assert {warning.code for warning in snapshot.warnings} == {"word_drawings_not_rendered"}

    second = extract_document(source, tmp_path / "second-evidence")
    assert second == snapshot


def test_extract_docx_allows_non_image_relationship_to_safe_package_root(
    tmp_path: Path,
) -> None:
    source = write_diagram_docx(
        tmp_path / "custom-xml.docx",
        package_root_relationship=True,
    )

    snapshot = extract_document(source, tmp_path / "evidence")

    assert len(snapshot.visual_assets) == 1
    assert snapshot.visual_assets[0].location.relationship_id == "rId1"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"external_relationship": True}, "External DOCX relationship"),
        ({"embedded_object": True}, "Embedded OLE/package"),
        ({"unsafe_xml": True}, "XML declarations are unsafe"),
    ],
)
def test_extract_docx_rejects_active_or_embedded_content(
    tmp_path: Path,
    kwargs: dict[str, bool],
    message: str,
) -> None:
    source = write_diagram_docx(tmp_path / "unsafe.docx", **kwargs)

    with pytest.raises(UnsafeDocumentError, match=message):
        extract_document(source, tmp_path / "evidence")

    assert not (tmp_path / "evidence").exists()
