"""Tests for bounded DOCX package inventory."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from visiogen.documents.errors import (
    DocumentExtractionError,
    DocumentLimitExceededError,
    EncryptedDocumentError,
    UnsafeDocumentError,
)
from visiogen.documents.safety import DocumentSafetyLimits, inspect_docx_archive


def write_docx(
    path: Path,
    *,
    extra: list[tuple[str, bytes]] | None = None,
    include_required: bool = True,
) -> Path:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        if include_required:
            archive.writestr("[Content_Types].xml", b"<Types/>")
            archive.writestr("word/document.xml", b"<document/>")
        for name, content in extra or []:
            archive.writestr(name, content)
    return path


def test_default_safety_limits_are_positive() -> None:
    limits = DocumentSafetyLimits()

    assert limits.max_file_bytes == 50 * 1024 * 1024
    assert limits.max_diagram_candidates == 8
    with pytest.raises(ValueError, match="must be positive"):
        DocumentSafetyLimits(max_archive_entries=0)


def test_docx_inventory_requires_core_package_members(tmp_path: Path) -> None:
    path = write_docx(tmp_path / "missing.docx", include_required=False)

    with pytest.raises(DocumentExtractionError, match="missing required members"):
        inspect_docx_archive(path)


def test_docx_inventory_rejects_traversal_and_duplicate_members(tmp_path: Path) -> None:
    traversal = write_docx(
        tmp_path / "traversal.docx",
        extra=[("../outside.xml", b"bad")],
    )
    with pytest.raises(UnsafeDocumentError, match="Unsafe DOCX member path"):
        inspect_docx_archive(traversal)

    with pytest.warns(UserWarning, match="Duplicate name"):
        duplicate = write_docx(
            tmp_path / "duplicate.docx",
            extra=[("word/document.xml", b"duplicate")],
        )
    with pytest.raises(UnsafeDocumentError, match="duplicate member"):
        inspect_docx_archive(duplicate)

    windows_traversal = write_docx(
        tmp_path / "windows-traversal.docx",
        extra=[("..\\outside.xml", b"bad")],
    )
    with pytest.raises(UnsafeDocumentError, match="Unsafe DOCX member path"):
        inspect_docx_archive(windows_traversal)


def test_docx_inventory_rejects_macros_and_resource_expansion(tmp_path: Path) -> None:
    macro = write_docx(
        tmp_path / "macro.docx",
        extra=[("word/vbaProject.bin", b"macro")],
    )
    with pytest.raises(UnsafeDocumentError, match="Macro-enabled"):
        inspect_docx_archive(macro)

    compressed = write_docx(
        tmp_path / "compressed.docx",
        extra=[("word/media/large.txt", b"x" * 50_000)],
    )
    with pytest.raises(DocumentLimitExceededError, match="compression ratio"):
        inspect_docx_archive(
            compressed,
            limits=DocumentSafetyLimits(max_compression_ratio=2),
        )


def test_docx_inventory_rejects_encrypted_symlink_and_activex_members(
    tmp_path: Path,
) -> None:
    encrypted = write_docx(tmp_path / "encrypted.docx")
    data = bytearray(encrypted.read_bytes())
    local = data.index(b"PK\x03\x04")
    central = data.index(b"PK\x01\x02")
    data[local + 6 : local + 8] = (1).to_bytes(2, "little")
    data[central + 8 : central + 10] = (1).to_bytes(2, "little")
    encrypted.write_bytes(data)
    with pytest.raises(EncryptedDocumentError, match="Encrypted DOCX member"):
        inspect_docx_archive(encrypted)

    symlink = tmp_path / "symlink.docx"
    with ZipFile(symlink, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("word/document.xml", b"<document/>")
        member = ZipInfo("word/media/link.png")
        member.create_system = 3
        member.external_attr = 0o120777 << 16
        archive.writestr(member, b"target.png")
    with pytest.raises(UnsafeDocumentError, match="symbolic link"):
        inspect_docx_archive(symlink)

    activex = write_docx(
        tmp_path / "activex.docx",
        extra=[("word/activeX/activeX1.bin", b"active")],
    )
    with pytest.raises(UnsafeDocumentError, match="ActiveX"):
        inspect_docx_archive(activex)


def test_docx_inventory_returns_validated_member_metadata(tmp_path: Path) -> None:
    path = write_docx(
        tmp_path / "valid.docx",
        extra=[("word/media/diagram.png", b"png")],
    )

    members = inspect_docx_archive(path)

    assert [member.name for member in members] == [
        "[Content_Types].xml",
        "word/document.xml",
        "word/media/diagram.png",
    ]


@pytest.mark.parametrize(
    ("limits", "message"),
    [
        (DocumentSafetyLimits(max_archive_entries=1), "too many members"),
        (DocumentSafetyLimits(max_archive_member_bytes=5), "member exceeds size"),
        (DocumentSafetyLimits(max_xml_member_bytes=5), "XML member exceeds size"),
        (DocumentSafetyLimits(max_archive_uncompressed_bytes=10), "total size"),
    ],
)
def test_docx_inventory_enforces_entry_and_expansion_limits(
    tmp_path: Path,
    limits: DocumentSafetyLimits,
    message: str,
) -> None:
    path = write_docx(tmp_path / "bounded.docx")

    with pytest.raises(DocumentLimitExceededError, match=message):
        inspect_docx_archive(path, limits=limits)
