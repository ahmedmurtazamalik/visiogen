"""Public deterministic PDF/DOCX-to-DocumentSnapshot orchestration."""

from __future__ import annotations

from pathlib import Path

from visiogen.documents.artifacts import publish_artifact_directory
from visiogen.documents.docx import extract_docx_snapshot
from visiogen.documents.models import DocumentSnapshot
from visiogen.documents.pdf import extract_pdf_snapshot
from visiogen.documents.safety import DEFAULT_SAFETY_LIMITS, DocumentSafetyLimits
from visiogen.documents.sniffing import admit_document


def extract_document(
    source: str | Path,
    artifact_dir: str | Path,
    *,
    limits: DocumentSafetyLimits = DEFAULT_SAFETY_LIMITS,
) -> DocumentSnapshot:
    """Safely admit and deterministically decompose one supported document."""

    admitted = admit_document(source, limits=limits)

    def build(stage: Path) -> DocumentSnapshot:
        if admitted.kind == "pdf":
            return extract_pdf_snapshot(admitted, stage, limits=limits)
        return extract_docx_snapshot(admitted, stage, limits=limits)

    result = publish_artifact_directory(artifact_dir, build)
    if not isinstance(result, DocumentSnapshot):
        raise TypeError("Document extractor returned an unexpected result")
    return result
