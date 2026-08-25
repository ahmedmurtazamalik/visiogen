"""Bounded and deterministic A2 crop/overview/tile preparation tests."""

import hashlib
import json
from pathlib import Path

from PIL import Image
import pytest

from visiogen.analysis.errors import ImagePreparationError
from visiogen.analysis.models import CandidateDecision
from visiogen.analysis.preparation import prepare_diagram_candidates
from visiogen.analysis.selection import discover_diagram_candidates
from visiogen.documents.models import (
    CoverageReport,
    DocumentSnapshot,
    SourceLocation,
    VisualAsset,
)
from visiogen.documents.safety import DocumentSafetyLimits


class CroppingClassifier:
    def classify(self, candidates):
        from visiogen.documents.models import NormalizedBox

        return tuple(
            CandidateDecision(
                candidate_id=candidate.id,
                label="diagram",
                confidence="high",
                reason="Reviewed test diagram",
                classifier="reviewed-fixture-v1",
                region=NormalizedBox(left=0.25, top=0.25, right=0.75, bottom=0.75),
            )
            for candidate in candidates
        )


def _snapshot_bundle(tmp_path: Path, *, width: int = 2400, height: int = 1200):
    bundle = tmp_path / "snapshot"
    assets = bundle / "assets"
    assets.mkdir(parents=True)
    path = assets / "page.png"
    Image.new("RGB", (width, height), (250, 250, 250)).save(path)
    data = path.read_bytes()
    asset = VisualAsset(
        id="asset-0001",
        media_type="image/png",
        origin="page_render",
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        artifact_path="assets/page.png",
        width_px=width,
        height_px=height,
        location=SourceLocation(page_number=1),
    )
    snapshot = DocumentSnapshot(
        source_id="sha256:" + "a" * 64,
        source_sha256="a" * 64,
        source_name="diagram.pdf",
        document_kind="pdf",
        media_type="application/pdf",
        byte_size=100,
        page_count=1,
        visual_assets=[asset],
        coverage=CoverageReport(
            native_text="complete",
            embedded_media="not_available",
            rendered_pages="complete",
        ),
    )
    return snapshot, bundle


def test_preparation_publishes_stable_crop_overview_and_tiles(tmp_path: Path) -> None:
    snapshot, bundle = _snapshot_bundle(tmp_path)
    discovery = discover_diagram_candidates(snapshot, classifier=CroppingClassifier())

    first = prepare_diagram_candidates(
        snapshot,
        discovery,
        bundle,
        tmp_path / "prepared-1",
        overview_edge=500,
        tile_edge=512,
        tile_overlap=64,
    )
    second = prepare_diagram_candidates(
        snapshot,
        discovery,
        bundle,
        tmp_path / "prepared-2",
        overview_edge=500,
        tile_edge=512,
        tile_overlap=64,
    )

    assert first == second
    derivatives = first.prepared_candidates[0].derivatives
    assert [item.kind for item in derivatives[:2]] == ["crop", "overview"]
    assert (derivatives[0].width_px, derivatives[0].height_px) == (1200, 600)
    assert (derivatives[1].width_px, derivatives[1].height_px) == (500, 250)
    assert len([item for item in derivatives if item.kind == "tile"]) == 6
    for derivative in derivatives:
        path = tmp_path / "prepared-1" / derivative.artifact_path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == derivative.sha256
    persisted = json.loads((tmp_path / "prepared-1" / "candidates.json").read_text())
    assert persisted == first.model_dump(mode="json")


def test_preparation_fails_atomically_when_tile_limit_is_exceeded(tmp_path: Path) -> None:
    snapshot, bundle = _snapshot_bundle(tmp_path, width=3000, height=3000)
    discovery = discover_diagram_candidates(snapshot, classifier=CroppingClassifier())
    output = tmp_path / "prepared"

    with pytest.raises(ImagePreparationError, match="more tiles"):
        prepare_diagram_candidates(
            snapshot,
            discovery,
            bundle,
            output,
            limits=DocumentSafetyLimits(max_tiles_per_candidate=2),
            tile_edge=512,
            tile_overlap=64,
        )

    assert not output.exists()


def test_preparation_rejects_an_asset_changed_after_snapshot(tmp_path: Path) -> None:
    snapshot, bundle = _snapshot_bundle(tmp_path)
    discovery = discover_diagram_candidates(snapshot, classifier=CroppingClassifier())
    (bundle / "assets/page.png").write_bytes(b"replaced")
    output = tmp_path / "prepared"

    with pytest.raises(ImagePreparationError, match="no longer matches"):
        prepare_diagram_candidates(snapshot, discovery, bundle, output)

    assert not output.exists()
