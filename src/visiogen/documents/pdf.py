"""Bounded PDF metadata, native-text, and page-render extraction through Poppler."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

from visiogen.documents.errors import (
    DocumentExtractionError,
    DocumentLimitExceededError,
    DocumentRenderError,
    EncryptedDocumentError,
    UnsafeDocumentError,
)
from visiogen.documents.image import inspect_raster_dimensions
from visiogen.documents.models import (
    CoverageReport,
    DocumentSnapshot,
    ExtractionWarning,
    NormalizedBox,
    SourceLocation,
    TextBlock,
    VisualAsset,
)
from visiogen.documents.safety import DocumentSafetyLimits
from visiogen.documents.sniffing import AdmittedDocument

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
_PAGE_SIZE = re.compile(
    r"(?:Page\s+\d+\s+)?size:\s*([0-9.]+)\s+x\s+([0-9.]+)\s+pts",
    re.IGNORECASE,
)
_PDF_NAME_TOKEN = re.compile(rb"/(?:#[0-9A-Fa-f]{2}|[^\x00\t\n\f\r ()<>\[\]{}/%])+")
_UNSAFE_PDF_ACTIONS = {
    b"JavaScript": "JavaScript",
    b"Launch": "launch action",
    b"URI": "external URI action",
    b"GoToR": "remote go-to action",
    b"GoToE": "embedded go-to action",
    b"SubmitForm": "form submission action",
    b"ImportData": "external data import action",
}


def _decode_pdf_name(token: bytes) -> bytes:
    """Decode hexadecimal escapes in one lexical PDF name token."""

    body = token[1:]
    return re.sub(
        rb"#([0-9A-Fa-f]{2})",
        lambda match: bytes((int(match.group(1), 16),)),
        body,
    )


def _contains_javascript_action(data: bytes) -> bool:
    """Conservatively recognize JavaScript action names across Poppler versions."""

    return any(
        _decode_pdf_name(match.group()) == b"JavaScript"
        for match in _PDF_NAME_TOKEN.finditer(data)
    )


def _pdf_names(data: bytes) -> set[bytes]:
    return {_decode_pdf_name(match.group()) for match in _PDF_NAME_TOKEN.finditer(data)}


def _resolve_command(name: str) -> str:
    command = shutil.which(name)
    if command is None:
        raise DocumentRenderError(f"Required Poppler command was not found: {name}")
    return command


def _run(
    runner: CommandRunner,
    args: list[str],
    *,
    limits: DocumentSafetyLimits,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = runner(
            args,
            text=True,
            capture_output=True,
            timeout=limits.external_command_timeout_seconds,
            env={
                "PATH": os.environ.get("PATH", ""),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
            },
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DocumentRenderError(f"Document command could not complete: {Path(args[0]).name}") from error
    if completed.returncode != 0:
        details = f"{completed.stdout}\n{completed.stderr}".lower()
        if "password" in details or "encrypted" in details:
            raise EncryptedDocumentError("Encrypted PDFs are not supported")
        raise DocumentRenderError(
            f"Document command failed with status {completed.returncode}: {Path(args[0]).name}"
        )
    return completed


def _pdf_metadata(
    admitted: AdmittedDocument,
    *,
    runner: CommandRunner,
    limits: DocumentSafetyLimits,
) -> tuple[int, list[tuple[float, float]]]:
    completed = _run(
        runner,
        [_resolve_command("pdfinfo"), "-box", str(admitted.path)],
        limits=limits,
    )
    values: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip().lower()] = value.strip()
    if values.get("encrypted", "no").lower().startswith("yes"):
        raise EncryptedDocumentError("Encrypted PDFs are not supported")
    try:
        page_count = int(values["pages"])
    except (KeyError, ValueError) as error:
        raise DocumentExtractionError("PDF metadata did not include a valid page count") from error
    if page_count <= 0:
        raise DocumentExtractionError("PDF contains no pages")
    if page_count > limits.max_pdf_pages:
        raise DocumentLimitExceededError("PDF exceeds the page count limit")
    size_output = completed.stdout
    if page_count > 1:
        size_output = _run(
            runner,
            [
                _resolve_command("pdfinfo"),
                "-f",
                "1",
                "-l",
                str(page_count),
                "-box",
                str(admitted.path),
            ],
            limits=limits,
        ).stdout
    sizes = [(float(width), float(height)) for width, height in _PAGE_SIZE.findall(size_output)]
    return page_count, sizes


def _pdf_security_scan(
    admitted: AdmittedDocument,
    *,
    runner: CommandRunner,
    limits: DocumentSafetyLimits,
) -> None:
    try:
        source_data = admitted.path.read_bytes()
    except OSError as error:
        raise DocumentExtractionError("PDF could not be read during security inspection") from error
    names = _pdf_names(source_data)
    if b"Encrypt" in names:
        raise EncryptedDocumentError("Encrypted PDFs are not supported")
    for action_name, description in _UNSAFE_PDF_ACTIONS.items():
        if action_name in names:
            raise UnsafeDocumentError(f"PDF {description} is not supported")
    javascript = _run(
        runner,
        [_resolve_command("pdfinfo"), "-js", str(admitted.path)],
        limits=limits,
    )
    if javascript.stdout.strip():
        raise UnsafeDocumentError("PDF JavaScript is not supported")
    attachments = _run(
        runner,
        [_resolve_command("pdfdetach"), "-list", str(admitted.path)],
        limits=limits,
    )
    first_line = attachments.stdout.strip().splitlines()[:1]
    if not first_line or not first_line[0].strip().lower().startswith("0 embedded files"):
        raise UnsafeDocumentError("PDF embedded files are not supported")


def _preflight_pixels(
    sizes: list[tuple[float, float]],
    *,
    page_count: int,
    dpi: int,
    limits: DocumentSafetyLimits,
) -> None:
    if not sizes:
        return
    if len(sizes) == 1 and page_count > 1:
        sizes *= page_count
    total = 0
    for width_points, height_points in sizes:
        pixels = math.ceil(width_points * dpi / 72) * math.ceil(height_points * dpi / 72)
        if pixels > limits.max_image_pixels:
            raise DocumentLimitExceededError("Rendered PDF page would exceed the pixel limit")
        total += pixels
    if total > limits.max_total_rendered_pixels:
        raise DocumentLimitExceededError("Rendered PDF pages would exceed the total pixel limit")


def _native_text_blocks(bbox_path: Path, page_count: int) -> list[TextBlock]:
    try:
        root = ET.parse(bbox_path).getroot()
    except (OSError, ET.ParseError) as error:
        raise DocumentExtractionError("Poppler produced malformed PDF text coordinates") from error
    blocks: list[TextBlock] = []
    pages = [element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "page"]
    for page_number, page in enumerate(pages, start=1):
        if page_number > page_count:
            break
        try:
            page_width = float(page.attrib["width"])
            page_height = float(page.attrib["height"])
        except (KeyError, ValueError) as error:
            raise DocumentExtractionError("PDF text page has invalid dimensions") from error
        if page_width <= 0 or page_height <= 0:
            raise DocumentExtractionError("PDF text page has non-positive dimensions")
        lines = [element for element in page.iter() if element.tag.rsplit("}", 1)[-1] == "line"]
        for line in lines:
            words = [element for element in line if element.tag.rsplit("}", 1)[-1] == "word"]
            text = " ".join((word.text or "").strip() for word in words).strip()
            if not text or not words:
                continue
            try:
                left = min(float(word.attrib["xMin"]) for word in words) / page_width
                top = min(float(word.attrib["yMin"]) for word in words) / page_height
                right = max(float(word.attrib["xMax"]) for word in words) / page_width
                bottom = max(float(word.attrib["yMax"]) for word in words) / page_height
            except (KeyError, ValueError) as error:
                raise DocumentExtractionError("PDF text word has invalid coordinates") from error
            left, top = max(0.0, left), max(0.0, top)
            right, bottom = min(1.0, right), min(1.0, bottom)
            if right <= left or bottom <= top:
                continue
            block_id = f"text-{len(blocks) + 1:04d}"
            blocks.append(
                TextBlock(
                    id=block_id,
                    text=text,
                    origin="native",
                    order=len(blocks),
                    location=SourceLocation(
                        page_number=page_number,
                        block_id=block_id,
                        bbox=NormalizedBox(left=left, top=top, right=right, bottom=bottom),
                    ),
                )
            )
    return blocks


def extract_pdf_snapshot(
    admitted: AdmittedDocument,
    stage: Path,
    *,
    limits: DocumentSafetyLimits,
    runner: CommandRunner = subprocess.run,
    render_dpi: int = 144,
) -> DocumentSnapshot:
    """Extract coordinate text and render every admitted PDF page to PNG."""

    if render_dpi <= 0:
        raise ValueError("PDF render DPI must be positive")
    _pdf_security_scan(admitted, runner=runner, limits=limits)
    page_count, sizes = _pdf_metadata(admitted, runner=runner, limits=limits)
    _preflight_pixels(sizes, page_count=page_count, dpi=render_dpi, limits=limits)
    assets_dir = stage / "assets"
    assets_dir.mkdir()
    bbox_path = stage / ".native-text.html"
    _run(
        runner,
        [
            _resolve_command("pdftotext"),
            "-bbox-layout",
            str(admitted.path),
            str(bbox_path),
        ],
        limits=limits,
    )
    text_blocks = _native_text_blocks(bbox_path, page_count)
    bbox_path.unlink(missing_ok=True)

    render_prefix = assets_dir / ".page"
    _run(
        runner,
        [
            _resolve_command("pdftoppm"),
            "-png",
            "-r",
            str(render_dpi),
            "-f",
            "1",
            "-l",
            str(page_count),
            str(admitted.path),
            str(render_prefix),
        ],
        limits=limits,
    )
    rendered = sorted(assets_dir.glob(".page-*.png"))
    if len(rendered) != page_count:
        raise DocumentRenderError("Poppler did not render the expected number of PDF pages")

    visual_assets: list[VisualAsset] = []
    total_pixels = 0
    for page_number, temporary in enumerate(rendered, start=1):
        data = temporary.read_bytes()
        dimensions = inspect_raster_dimensions(data, limits=limits)
        total_pixels += dimensions.pixels
        if total_pixels > limits.max_total_rendered_pixels:
            raise DocumentLimitExceededError("Rendered PDF pages exceed the total pixel limit")
        asset_id = f"page-{page_number:04d}"
        filename = f"{asset_id}.png"
        destination = assets_dir / filename
        temporary.replace(destination)
        visual_assets.append(
            VisualAsset(
                id=asset_id,
                media_type="image/png",
                origin="page_render",
                sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data),
                artifact_path=f"assets/{filename}",
                width_px=dimensions.width,
                height_px=dimensions.height,
                location=SourceLocation(page_number=page_number),
            )
        )

    warnings: list[ExtractionWarning] = []
    if not text_blocks:
        warnings.append(
            ExtractionWarning(
                code="no_native_pdf_text",
                message="PDF pages rendered successfully but contained no extractable native text",
                severity="info",
            )
        )
    snapshot = DocumentSnapshot(
        source_id=f"sha256:{admitted.sha256}",
        source_sha256=admitted.sha256,
        source_name=admitted.path.name,
        document_kind="pdf",
        media_type=admitted.media_type,
        byte_size=admitted.byte_size,
        page_count=page_count,
        text_blocks=text_blocks,
        visual_assets=visual_assets,
        warnings=warnings,
        coverage=CoverageReport(
            native_text="complete",
            embedded_media="not_available",
            rendered_pages="complete",
            word_drawings="not_available",
        ),
    )
    (stage / "snapshot.json").write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return snapshot
