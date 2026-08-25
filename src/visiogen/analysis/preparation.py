"""Bounded crop, overview, and tile preparation for selected candidates."""

from __future__ import annotations

import hashlib
from io import BytesIO
import json
import math
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from visiogen.analysis.errors import ImagePreparationError
from visiogen.analysis.models import (
    CandidateDiscovery,
    CandidatePreparation,
    DiagramCandidate,
    PreparedCandidate,
    PreparedDerivative,
)
from visiogen.documents.artifacts import publish_artifact_directory
from visiogen.documents.models import DocumentSnapshot, NormalizedBox, VisualAsset
from visiogen.documents.safety import DEFAULT_SAFETY_LIMITS, DocumentSafetyLimits

_DEFAULT_OVERVIEW_EDGE = 1_600
_DEFAULT_TILE_EDGE = 1_024
_DEFAULT_TILE_OVERLAP = 128


def _full_region() -> NormalizedBox:
    return NormalizedBox(left=0, top=0, right=1, bottom=1)


def _asset_bytes(snapshot_dir: Path, asset: VisualAsset) -> bytes:
    if snapshot_dir.is_symlink() or not snapshot_dir.is_dir():
        raise ImagePreparationError("Document snapshot directory must be a real directory")
    root = snapshot_dir.resolve()
    path = snapshot_dir / asset.artifact_path
    try:
        path.resolve().relative_to(root)
    except ValueError as error:
        raise ImagePreparationError("Visual asset escaped the snapshot directory") from error
    if path.is_symlink() or not path.is_file():
        raise ImagePreparationError(f"Visual asset is missing or unsafe: {asset.id}")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ImagePreparationError(f"Visual asset could not be read: {asset.id}") from error
    if len(data) != asset.byte_size or hashlib.sha256(data).hexdigest() != asset.sha256:
        raise ImagePreparationError(f"Visual asset no longer matches its snapshot: {asset.id}")
    return data


def _crop_bounds(region: NormalizedBox, width: int, height: int) -> tuple[int, int, int, int]:
    left = max(0, min(width - 1, math.floor(region.left * width)))
    top = max(0, min(height - 1, math.floor(region.top * height)))
    right = max(left + 1, min(width, math.ceil(region.right * width)))
    bottom = max(top + 1, min(height, math.ceil(region.bottom * height)))
    return left, top, right, bottom


def _axis_positions(length: int, tile_edge: int, overlap: int) -> list[int]:
    if length <= tile_edge:
        return [0]
    step = tile_edge - overlap
    positions = list(range(0, length - tile_edge + 1, step))
    final = length - tile_edge
    if positions[-1] != final:
        positions.append(final)
    return positions


def _write_png(image: Image.Image, path: Path) -> tuple[str, int]:
    image.save(path, format="PNG", compress_level=9, optimize=False)
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _source_subregion(
    candidate_region: NormalizedBox,
    crop_width: int,
    crop_height: int,
    box: tuple[int, int, int, int],
) -> NormalizedBox:
    left, top, right, bottom = box
    region_width = candidate_region.right - candidate_region.left
    region_height = candidate_region.bottom - candidate_region.top
    return NormalizedBox(
        left=candidate_region.left + region_width * (left / crop_width),
        top=candidate_region.top + region_height * (top / crop_height),
        right=candidate_region.left + region_width * (right / crop_width),
        bottom=candidate_region.top + region_height * (bottom / crop_height),
    )


def _prepare_one(
    candidate: DiagramCandidate,
    asset: VisualAsset,
    source_data: bytes,
    assets_dir: Path,
    *,
    limits: DocumentSafetyLimits,
    overview_edge: int,
    tile_edge: int,
    tile_overlap: int,
) -> PreparedCandidate:
    region = candidate.decision.region or _full_region()
    try:
        with Image.open(BytesIO(source_data)) as opened:
            if opened.width * opened.height > limits.max_image_pixels:
                raise ImagePreparationError("Candidate image exceeds the decoded pixel limit")
            opened.load()
            oriented = ImageOps.exif_transpose(opened)
            if oriented.width * oriented.height > limits.max_image_pixels:
                raise ImagePreparationError("Oriented candidate exceeds the decoded pixel limit")
            pixels = oriented.convert("RGBA")
    except ImagePreparationError:
        raise
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ImagePreparationError(f"Candidate image could not be decoded: {asset.id}") from error

    bounds = _crop_bounds(region, pixels.width, pixels.height)
    crop = pixels.crop(bounds)
    if crop.width * crop.height > limits.max_image_pixels:
        raise ImagePreparationError("Candidate crop exceeds the decoded pixel limit")

    derivatives: list[PreparedDerivative] = []
    crop_name = f"{candidate.id}-crop.png"
    crop_path = assets_dir / crop_name
    sha256, byte_size = _write_png(crop, crop_path)
    derivatives.append(
        PreparedDerivative(
            id=f"{candidate.id}-crop",
            kind="crop",
            artifact_path=f"assets/{crop_name}",
            sha256=sha256,
            byte_size=byte_size,
            width_px=crop.width,
            height_px=crop.height,
            source_region=region,
        )
    )

    overview = crop.copy()
    overview.thumbnail((overview_edge, overview_edge), Image.Resampling.LANCZOS)
    overview_name = f"{candidate.id}-overview.png"
    overview_path = assets_dir / overview_name
    sha256, byte_size = _write_png(overview, overview_path)
    derivatives.append(
        PreparedDerivative(
            id=f"{candidate.id}-overview",
            kind="overview",
            artifact_path=f"assets/{overview_name}",
            sha256=sha256,
            byte_size=byte_size,
            width_px=overview.width,
            height_px=overview.height,
            source_region=region,
        )
    )

    x_positions = _axis_positions(crop.width, tile_edge, tile_overlap)
    y_positions = _axis_positions(crop.height, tile_edge, tile_overlap)
    tile_boxes = [
        (x, y, min(x + tile_edge, crop.width), min(y + tile_edge, crop.height))
        for y in y_positions
        for x in x_positions
    ]
    if len(tile_boxes) > 1:
        if len(tile_boxes) > limits.max_tiles_per_candidate:
            raise ImagePreparationError("Candidate requires more tiles than the configured limit")
        for index, box in enumerate(tile_boxes, start=1):
            tile = crop.crop(box)
            name = f"{candidate.id}-tile-{index:03d}.png"
            path = assets_dir / name
            sha256, byte_size = _write_png(tile, path)
            derivatives.append(
                PreparedDerivative(
                    id=f"{candidate.id}-tile-{index:03d}",
                    kind="tile",
                    artifact_path=f"assets/{name}",
                    sha256=sha256,
                    byte_size=byte_size,
                    width_px=tile.width,
                    height_px=tile.height,
                    source_region=_source_subregion(
                        region,
                        crop.width,
                        crop.height,
                        box,
                    ),
                )
            )
    return PreparedCandidate(candidate_id=candidate.id, derivatives=derivatives)


def prepare_diagram_candidates(
    snapshot: DocumentSnapshot,
    discovery: CandidateDiscovery,
    snapshot_dir: str | Path,
    output_dir: str | Path,
    *,
    limits: DocumentSafetyLimits = DEFAULT_SAFETY_LIMITS,
    overview_edge: int = _DEFAULT_OVERVIEW_EDGE,
    tile_edge: int = _DEFAULT_TILE_EDGE,
    tile_overlap: int = _DEFAULT_TILE_OVERLAP,
) -> CandidatePreparation:
    """Decode and atomically publish model-ready images for selected candidates."""

    if discovery.source_id != snapshot.source_id:
        raise ImagePreparationError("Candidate discovery belongs to a different document")
    if overview_edge <= 0 or tile_edge <= 0 or tile_overlap < 0 or tile_overlap >= tile_edge:
        raise ValueError("Image preparation dimensions or overlap are invalid")
    assets_by_id = {asset.id: asset for asset in snapshot.visual_assets}
    source_root = Path(snapshot_dir)

    def build(stage: Path) -> CandidatePreparation:
        assets_dir = stage / "assets"
        assets_dir.mkdir()
        prepared: list[PreparedCandidate] = []
        for candidate in discovery.candidates:
            if candidate.disposition != "selected":
                continue
            try:
                asset = assets_by_id[candidate.primary_asset_id]
            except KeyError as error:
                raise ImagePreparationError(
                    f"Candidate references an unknown visual asset: {candidate.primary_asset_id}"
                ) from error
            prepared.append(
                _prepare_one(
                    candidate,
                    asset,
                    _asset_bytes(source_root, asset),
                    assets_dir,
                    limits=limits,
                    overview_edge=overview_edge,
                    tile_edge=tile_edge,
                    tile_overlap=tile_overlap,
                )
            )
        result = CandidatePreparation(
            discovery=discovery,
            prepared_candidates=prepared,
        )
        (stage / "candidates.json").write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        )
        return result

    result = publish_artifact_directory(output_dir, build)
    if not isinstance(result, CandidatePreparation):
        raise TypeError("Candidate preparation returned an unexpected result")
    return result
