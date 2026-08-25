"""Real Poppler acceptance for deterministic PDF text and page rendering."""

import json
from pathlib import Path
import shutil

import pytest

from fixture_builders import write_text_pdf
from visiogen.documents.errors import (
    DocumentLimitExceededError,
    DocumentRenderError,
    UnsafeDocumentError,
)
from visiogen.documents.extractor import extract_document
from visiogen.documents.safety import DocumentSafetyLimits


POPPLER_AVAILABLE = all(
    shutil.which(command) for command in ("pdfinfo", "pdfdetach", "pdftotext", "pdftoppm")
)


@pytest.mark.integration
@pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler commands are not installed")
def test_extract_pdf_writes_coordinate_text_and_real_page_render(tmp_path: Path) -> None:
    source = write_text_pdf(tmp_path / "diagram.pdf")
    output = tmp_path / "evidence"

    snapshot = extract_document(source, output)

    assert snapshot.document_kind == "pdf"
    assert snapshot.page_count == 1
    assert "Sensor to Processor" in " ".join(block.text for block in snapshot.text_blocks)
    assert all(block.location.bbox is not None for block in snapshot.text_blocks)
    assert len(snapshot.visual_assets) == 1
    page = snapshot.visual_assets[0]
    assert page.origin == "page_render"
    assert page.width_px == 1224
    assert page.height_px == 1584
    assert (output / page.artifact_path).read_bytes().startswith(b"\x89PNG")
    assert json.loads((output / "snapshot.json").read_text()) == snapshot.model_dump(mode="json")
    assert snapshot.coverage.rendered_pages == "complete"

    second = extract_document(source, tmp_path / "second-evidence")
    assert second == snapshot


@pytest.mark.integration
@pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler commands are not installed")
def test_extract_pdf_rejects_javascript_and_malformed_sources(tmp_path: Path) -> None:
    javascript = write_text_pdf(tmp_path / "javascript.pdf", javascript=True)
    with pytest.raises(UnsafeDocumentError, match="JavaScript"):
        extract_document(javascript, tmp_path / "javascript-evidence")
    assert not (tmp_path / "javascript-evidence").exists()

    malformed = tmp_path / "malformed.pdf"
    malformed.write_bytes(b"%PDF-1.7\nnot a valid package")
    with pytest.raises(DocumentRenderError, match="pdfinfo"):
        extract_document(malformed, tmp_path / "malformed-evidence")
    assert not (tmp_path / "malformed-evidence").exists()


@pytest.mark.integration
@pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler commands are not installed")
def test_extract_pdf_enforces_render_pixel_preflight(tmp_path: Path) -> None:
    source = write_text_pdf(tmp_path / "large-render.pdf")

    with pytest.raises(DocumentLimitExceededError, match="pixel limit"):
        extract_document(
            source,
            tmp_path / "evidence",
            limits=DocumentSafetyLimits(max_image_pixels=1_000),
        )

    assert not (tmp_path / "evidence").exists()
