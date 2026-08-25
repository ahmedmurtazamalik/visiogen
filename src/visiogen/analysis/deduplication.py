"""Conservative visual matching for embedded-image/page-render representations."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from visiogen.analysis.errors import ImagePreparationError
from visiogen.analysis.models import DuplicateMatch
from visiogen.documents.models import DocumentSnapshot, NormalizedBox, VisualAsset
from visiogen.documents.safety import DEFAULT_SAFETY_LIMITS, DocumentSafetyLimits

_SEARCH_LONG_EDGE = 64
_MIN_TEMPLATE_EDGE = 12
_DEFAULT_MIN_SIMILARITY = 0.89


def _verified_image(
    snapshot_dir: Path,
    asset: VisualAsset,
    limits: DocumentSafetyLimits,
) -> Image.Image:
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
    try:
        with Image.open(BytesIO(data)) as opened:
            if opened.width * opened.height > limits.max_image_pixels:
                raise ImagePreparationError("Candidate image exceeds the decoded pixel limit")
            opened.load()
            return ImageOps.exif_transpose(opened).convert("L")
    except ImagePreparationError:
        raise
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ImagePreparationError(f"Candidate image could not be decoded: {asset.id}") from error


def _fit_long_edge(image: Image.Image, edge: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return copy


def _edge_map(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.FIND_EDGES).point(lambda value: 255 if value >= 36 else 0)


def _difference(first: Image.Image, second: Image.Image) -> float:
    gray = ImageStat.Stat(ImageChops.difference(first, second)).mean[0] / 255
    edges = ImageStat.Stat(
        ImageChops.difference(_edge_map(first), _edge_map(second))
    ).mean[0] / 255
    return 0.35 * gray + 0.65 * edges


def _positions(length: int, window: int, step: int) -> list[int]:
    final = length - window
    values = list(range(0, final + 1, step))
    if values[-1] != final:
        values.append(final)
    return values


def _best_containment(
    embedded: Image.Image,
    page: Image.Image,
) -> tuple[float, tuple[int, int, int, int]] | None:
    page_search = _fit_long_edge(page, _SEARCH_LONG_EDGE)
    scale_x = page.width / page_search.width
    scale_y = page.height / page_search.height
    aspect = embedded.width / embedded.height
    best_score = 1.0
    best_box: tuple[int, int, int, int] | None = None
    min_width = max(_MIN_TEMPLATE_EDGE, round(page_search.width * 0.2))
    max_width = round(page_search.width * 0.95)
    for width in range(min_width, max_width + 1, 2):
        height = round(width / aspect)
        if height < _MIN_TEMPLATE_EDGE or height > page_search.height:
            continue
        template = embedded.resize((width, height), Image.Resampling.LANCZOS)
        edge_energy = ImageStat.Stat(_edge_map(template)).mean[0] / 255
        if edge_energy < 0.015:
            continue
        step = max(2, min(width, height) // 8)
        for top in _positions(page_search.height, height, step):
            for left in _positions(page_search.width, width, step):
                region = page_search.crop((left, top, left + width, top + height))
                score = _difference(template, region)
                if score < best_score:
                    best_score = score
                    best_box = (left, top, left + width, top + height)
    if best_box is None:
        return None
    left, top, right, bottom = best_box
    original_box = (
        round(left * scale_x),
        round(top * scale_y),
        min(page.width, round(right * scale_x)),
        min(page.height, round(bottom * scale_y)),
    )
    return 1 - best_score, original_box


def find_embedded_page_duplicates(
    snapshot: DocumentSnapshot,
    snapshot_dir: str | Path,
    *,
    limits: DocumentSafetyLimits = DEFAULT_SAFETY_LIMITS,
    min_similarity: float = _DEFAULT_MIN_SIMILARITY,
) -> tuple[DuplicateMatch, ...]:
    """Return only high-confidence embedded/page matches, never page/page matches."""

    if not 0 < min_similarity <= 1:
        raise ValueError("min_similarity must be within (0, 1]")
    embedded_assets = [asset for asset in snapshot.visual_assets if asset.origin == "embedded"]
    page_assets = [asset for asset in snapshot.visual_assets if asset.origin == "page_render"]
    if len(embedded_assets) * len(page_assets) > limits.max_perceptual_comparisons:
        raise ImagePreparationError(
            "Document exceeds the configured perceptual duplicate comparison limit"
        )
    root = Path(snapshot_dir)
    embedded_images = {
        asset.id: _verified_image(root, asset, limits) for asset in embedded_assets
    }
    page_images = {asset.id: _verified_image(root, asset, limits) for asset in page_assets}
    matches: list[DuplicateMatch] = []
    for embedded_asset in embedded_assets:
        embedded = embedded_images[embedded_asset.id]
        best: tuple[float, VisualAsset, tuple[int, int, int, int], tuple[int, int]] | None = None
        for page_asset in page_assets:
            if embedded_asset.sha256 == page_asset.sha256:
                continue
            page = page_images[page_asset.id]
            result = _best_containment(embedded, page)
            if result is None:
                continue
            similarity, box = result
            if best is None or similarity > best[0]:
                best = (similarity, page_asset, box, page.size)
        if best is None or best[0] < min_similarity:
            continue
        similarity, page_asset, box, page_size = best
        left, top, right, bottom = box
        matches.append(
            DuplicateMatch(
                first_asset_id=embedded_asset.id,
                second_asset_id=page_asset.id,
                method="embedded_page_visual_v1",
                similarity=similarity,
                page_region=NormalizedBox(
                    left=left / page_size[0],
                    top=top / page_size[1],
                    right=right / page_size[0],
                    bottom=bottom / page_size[1],
                ),
            )
        )
    return tuple(matches)
