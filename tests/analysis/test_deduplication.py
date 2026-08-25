"""Perceptual embedded-image/page-render grouping with false-match controls."""

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw

from visiogen.analysis.deduplication import find_embedded_page_duplicates
from visiogen.analysis.selection import discover_diagram_candidates
from visiogen.documents.models import (
    CoverageReport,
    DocumentSnapshot,
    SourceLocation,
    VisualAsset,
)


def _diagram() -> Image.Image:
    image = Image.new("RGB", (320, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 55, 115, 125), outline="black", width=5)
    draw.rectangle((205, 55, 300, 125), outline="black", width=5)
    draw.line((115, 90, 205, 90), fill="black", width=5)
    draw.polygon(((205, 90), (190, 80), (190, 100)), fill="black")
    draw.text((43, 82), "Input", fill="black")
    draw.text((225, 82), "Output", fill="black")
    return image


def _write_asset(
    root: Path,
    asset_id: str,
    image: Image.Image,
    *,
    origin: str,
    page: int | None,
) -> VisualAsset:
    path = root / "assets" / f"{asset_id}.png"
    image.save(path, format="PNG", compress_level=9)
    data = path.read_bytes()
    return VisualAsset(
        id=asset_id,
        media_type="image/png",
        origin=origin,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        artifact_path=f"assets/{asset_id}.png",
        width_px=image.width,
        height_px=image.height,
        location=SourceLocation(page_number=page),
    )


def _snapshot(tmp_path: Path) -> tuple[DocumentSnapshot, Path]:
    bundle = tmp_path / "snapshot"
    (bundle / "assets").mkdir(parents=True)
    embedded = _diagram()
    matching_page = Image.new("RGB", (800, 1000), "white")
    matching_page.paste(embedded.resize((480, 270)), (160, 250))
    unrelated_page = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(unrelated_page)
    for index, height in enumerate((100, 230, 170, 310)):
        left = 120 + index * 130
        draw.rectangle((left, 700 - height, left + 80, 700), fill="steelblue")
    assets = [
        _write_asset(bundle, "embedded", embedded, origin="embedded", page=None),
        _write_asset(bundle, "matching-page", matching_page, origin="page_render", page=1),
        _write_asset(bundle, "chart-page", unrelated_page, origin="page_render", page=2),
    ]
    snapshot = DocumentSnapshot(
        source_id="sha256:" + "a" * 64,
        source_sha256="a" * 64,
        source_name="mixed.docx",
        document_kind="docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        byte_size=100,
        page_count=2,
        visual_assets=assets,
        coverage=CoverageReport(
            native_text="complete",
            embedded_media="complete",
            rendered_pages="complete",
        ),
    )
    return snapshot, bundle


def test_perceptual_match_finds_embedded_page_region_without_matching_chart(
    tmp_path: Path,
) -> None:
    snapshot, bundle = _snapshot(tmp_path)

    matches = find_embedded_page_duplicates(snapshot, bundle)

    assert len(matches) == 1
    match = matches[0]
    assert match.first_asset_id == "embedded"
    assert match.second_asset_id == "matching-page"
    assert match.similarity >= 0.89
    assert match.page_region is not None
    assert 0.15 <= match.page_region.left <= 0.25
    assert 0.2 <= match.page_region.top <= 0.3

    discovery = discover_diagram_candidates(snapshot, snapshot_dir=bundle)
    assert discovery.coverage.source_assets == 3
    assert discovery.coverage.unique_candidates == 2
    assert discovery.coverage.duplicate_assets_grouped == 1
    grouped = discovery.candidates[0]
    assert grouped.primary_asset_id == "embedded"
    assert grouped.source_asset_ids == ["embedded", "matching-page"]
    assert grouped.duplicate_matches[0].method == "embedded_page_visual_v1"


def test_perceptual_match_rejects_an_unrelated_chart(tmp_path: Path) -> None:
    snapshot, bundle = _snapshot(tmp_path)
    snapshot.visual_assets = [snapshot.visual_assets[0], snapshot.visual_assets[2]]

    assert find_embedded_page_duplicates(snapshot, bundle) == ()
