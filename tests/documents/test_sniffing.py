"""Tests for signature-based document admission and immutable identity."""

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from visiogen.documents.errors import (
    DocumentLimitExceededError,
    DocumentTypeMismatchError,
    UnsupportedDocumentError,
    UnsafeDocumentError,
)
from visiogen.documents.safety import DocumentSafetyLimits
from visiogen.documents.sniffing import admit_document


def write_minimal_docx(path: Path) -> Path:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("word/document.xml", b"<document/>")
    return path


def test_admit_pdf_uses_signature_and_records_identity(tmp_path: Path) -> None:
    content = b"%PDF-1.7\nminimal admission fixture\n%%EOF\n"
    path = tmp_path / "example.pdf"
    path.write_bytes(content)

    admitted = admit_document(path)

    assert admitted.kind == "pdf"
    assert admitted.media_type == "application/pdf"
    assert admitted.byte_size == len(content)
    assert admitted.sha256 == hashlib.sha256(content).hexdigest()
    assert admitted.archive_members == ()


def test_admit_docx_validates_package_before_returning(tmp_path: Path) -> None:
    path = write_minimal_docx(tmp_path / "example.docx")

    admitted = admit_document(path)

    assert admitted.kind == "docx"
    assert {member.name for member in admitted.archive_members} == {
        "[Content_Types].xml",
        "word/document.xml",
    }


def test_admission_rejects_extension_mismatch_and_unknown_content(tmp_path: Path) -> None:
    disguised = tmp_path / "example.docx"
    disguised.write_bytes(b"%PDF-1.7\n%%EOF")
    with pytest.raises(DocumentTypeMismatchError, match="content is PDF"):
        admit_document(disguised)

    unknown = tmp_path / "example.pdf"
    unknown.write_bytes(b"not a document")
    with pytest.raises(UnsupportedDocumentError, match="not a recognized"):
        admit_document(unknown)


def test_admission_rejects_symlink_and_file_size_limit(tmp_path: Path) -> None:
    target = tmp_path / "target.pdf"
    target.write_bytes(b"%PDF-1.7\n%%EOF")
    link = tmp_path / "link.pdf"
    link.symlink_to(target)
    with pytest.raises(UnsafeDocumentError, match="symbolic link"):
        admit_document(link)

    with pytest.raises(DocumentLimitExceededError, match="file size"):
        admit_document(target, limits=DocumentSafetyLimits(max_file_bytes=4))
