"""Tests for normalized provider-independent document contracts."""

import pytest
from pydantic import ValidationError

from visiogen.documents.models import (
    CoverageReport,
    DocumentSnapshot,
    NormalizedBox,
    SourceLocation,
    TextBlock,
    VisualAsset,
)


SHA256 = "a" * 64


def coverage() -> CoverageReport:
    return CoverageReport(
        native_text="complete",
        embedded_media="complete",
        rendered_pages="not_available",
    )


def test_normalized_box_requires_positive_bounded_area() -> None:
    assert NormalizedBox(left=0, top=0.2, right=1, bottom=0.8).right == 1

    with pytest.raises(ValidationError, match="positive width and height"):
        NormalizedBox(left=0.5, top=0, right=0.5, bottom=1)
    with pytest.raises(ValidationError):
        NormalizedBox(left=-0.1, top=0, right=1, bottom=1)


def test_visual_asset_dimensions_must_be_supplied_together() -> None:
    with pytest.raises(ValidationError, match="supplied together"):
        VisualAsset(
            id="asset-1",
            media_type="image/png",
            origin="embedded",
            sha256=SHA256,
            byte_size=12,
            artifact_path="assets/asset-1.png",
            width_px=100,
            location=SourceLocation(page_number=1),
        )

    with pytest.raises(ValidationError, match="inside the bundle"):
        VisualAsset(
            id="asset-1",
            media_type="image/png",
            origin="embedded",
            sha256=SHA256,
            byte_size=12,
            artifact_path="..\\outside.png",
            width_px=100,
            height_px=100,
            location=SourceLocation(page_number=1),
        )


def test_snapshot_rejects_duplicate_ids_and_unknown_asset_references() -> None:
    block = TextBlock(
        id="text-1",
        text="Figure 1",
        origin="caption",
        order=0,
        location=SourceLocation(page_number=1),
    )
    base = {
        "source_id": "source-1",
        "source_sha256": SHA256,
        "source_name": "example.pdf",
        "document_kind": "pdf",
        "media_type": "application/pdf",
        "byte_size": 100,
        "page_count": 1,
        "coverage": coverage(),
    }

    with pytest.raises(ValidationError, match="Text block IDs must be unique"):
        DocumentSnapshot(**base, text_blocks=[block, block])

    bad_reference = block.model_copy(
        update={"location": SourceLocation(page_number=1, asset_id="missing")}
    )
    with pytest.raises(ValidationError, match="unknown asset"):
        DocumentSnapshot(**base, text_blocks=[bad_reference])


def test_snapshot_accepts_resolved_asset_evidence() -> None:
    asset = VisualAsset(
        id="asset-1",
        media_type="image/png",
        origin="page_render",
        sha256=SHA256,
        byte_size=12,
        artifact_path="assets/asset-1.png",
        width_px=100,
        height_px=80,
        location=SourceLocation(page_number=1),
    )
    block = TextBlock(
        id="text-1",
        text="Processor",
        origin="ocr",
        order=0,
        location=SourceLocation(page_number=1, asset_id="asset-1"),
    )

    snapshot = DocumentSnapshot(
        source_id="source-1",
        source_sha256=SHA256,
        source_name="example.pdf",
        document_kind="pdf",
        media_type="application/pdf",
        byte_size=100,
        page_count=1,
        text_blocks=[block],
        visual_assets=[asset],
        coverage=coverage(),
    )

    assert snapshot.text_blocks[0].location.asset_id == "asset-1"
