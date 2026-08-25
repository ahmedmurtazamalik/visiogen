"""Signature-based document admission before parsing or provider calls."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from visiogen.documents.errors import (
    DocumentLimitExceededError,
    DocumentTypeMismatchError,
    UnsupportedDocumentError,
    UnsafeDocumentError,
)
from visiogen.documents.models import DocumentKind
from visiogen.documents.safety import (
    DEFAULT_SAFETY_LIMITS,
    ArchiveMember,
    DocumentSafetyLimits,
    inspect_docx_archive,
)

_MEDIA_TYPES: dict[DocumentKind, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass(frozen=True, slots=True)
class AdmittedDocument:
    """Immutable identity and inspected package inventory for an admitted source."""

    path: Path
    kind: DocumentKind
    media_type: str
    byte_size: int
    sha256: str
    archive_members: tuple[ArchiveMember, ...] = ()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _detect_kind(path: Path) -> DocumentKind:
    try:
        with path.open("rb") as stream:
            prefix = stream.read(1024)
    except OSError as error:
        raise UnsupportedDocumentError("Document could not be read") from error
    if b"%PDF-" in prefix:
        return "pdf"
    if prefix.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "docx"
    raise UnsupportedDocumentError("Input is not a recognized PDF or DOCX package")


def admit_document(
    source: str | Path,
    *,
    limits: DocumentSafetyLimits = DEFAULT_SAFETY_LIMITS,
) -> AdmittedDocument:
    """Admit one local PDF or DOCX after identity, type, and package checks."""

    path = Path(source)
    if path.is_symlink():
        raise UnsafeDocumentError("Document source must not be a symbolic link")
    if not path.is_file():
        raise UnsupportedDocumentError("Document source is not a regular file")
    try:
        byte_size = path.stat().st_size
    except OSError as error:
        raise UnsupportedDocumentError("Document metadata could not be read") from error
    if byte_size <= 0:
        raise UnsupportedDocumentError("Document source is empty")
    if byte_size > limits.max_file_bytes:
        raise DocumentLimitExceededError("Document exceeds the input file size limit")

    kind = _detect_kind(path)
    expected_suffix = f".{kind}"
    if path.suffix.lower() != expected_suffix:
        raise DocumentTypeMismatchError(
            f"Document content is {kind.upper()} but extension is {path.suffix or '<none>'}"
        )
    members = inspect_docx_archive(path, limits=limits) if kind == "docx" else ()
    return AdmittedDocument(
        path=path.resolve(),
        kind=kind,
        media_type=_MEDIA_TYPES[kind],
        byte_size=byte_size,
        sha256=_sha256(path),
        archive_members=members,
    )
