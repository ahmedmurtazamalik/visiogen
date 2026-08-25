"""Resource limits and safe DOCX ZIP inventory without extracting members."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from visiogen.documents.errors import (
    DocumentExtractionError,
    DocumentLimitExceededError,
    EncryptedDocumentError,
    UnsafeDocumentError,
)


@dataclass(frozen=True, slots=True)
class DocumentSafetyLimits:
    """Explicit resource limits applied before expensive parsing or rendering."""

    max_file_bytes: int = 50 * 1024 * 1024
    max_pdf_pages: int = 100
    max_archive_entries: int = 2_000
    max_archive_uncompressed_bytes: int = 250 * 1024 * 1024
    max_archive_member_bytes: int = 50 * 1024 * 1024
    max_xml_member_bytes: int = 20 * 1024 * 1024
    max_compression_ratio: float = 100.0
    max_image_pixels: int = 40_000_000
    max_total_rendered_pixels: int = 500_000_000
    max_diagram_candidates: int = 8
    max_tiles_per_candidate: int = 24
    max_model_calls_per_candidate: int = 4
    external_command_timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        for field in fields(self):
            name = field.name
            value = getattr(self, name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")


DEFAULT_SAFETY_LIMITS = DocumentSafetyLimits()


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    """Validated metadata for one DOCX package member."""

    name: str
    compressed_bytes: int
    uncompressed_bytes: int


def _validate_member_name(info: ZipInfo) -> None:
    name = info.filename
    path = PurePosixPath(name)
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise UnsafeDocumentError(f"Unsafe DOCX member path: {name!r}")
    unix_mode = info.external_attr >> 16
    if unix_mode and (unix_mode & 0o170000) == 0o120000:
        raise UnsafeDocumentError(f"DOCX member must not be a symbolic link: {name}")


def inspect_docx_archive(
    path: str | Path,
    *,
    limits: DocumentSafetyLimits = DEFAULT_SAFETY_LIMITS,
) -> tuple[ArchiveMember, ...]:
    """Validate a DOCX ZIP inventory without extracting or parsing member content."""

    try:
        archive = ZipFile(path)
    except (BadZipFile, OSError) as error:
        raise DocumentExtractionError("DOCX package is not a readable ZIP archive") from error

    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_archive_entries:
            raise DocumentLimitExceededError("DOCX archive contains too many members")
        names: set[str] = set()
        members: list[ArchiveMember] = []
        total_uncompressed = 0
        for info in infos:
            _validate_member_name(info)
            if info.filename in names:
                raise UnsafeDocumentError(f"DOCX archive has duplicate member: {info.filename}")
            names.add(info.filename)
            if info.flag_bits & 0x1:
                raise EncryptedDocumentError(f"Encrypted DOCX member: {info.filename}")
            if info.file_size > limits.max_archive_member_bytes:
                raise DocumentLimitExceededError(
                    f"DOCX member exceeds size limit: {info.filename}"
                )
            if info.filename.lower().endswith(".xml") and info.file_size > limits.max_xml_member_bytes:
                raise DocumentLimitExceededError(
                    f"DOCX XML member exceeds size limit: {info.filename}"
                )
            total_uncompressed += info.file_size
            if total_uncompressed > limits.max_archive_uncompressed_bytes:
                raise DocumentLimitExceededError("DOCX archive expands beyond total size limit")
            if info.file_size:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > limits.max_compression_ratio:
                    raise DocumentLimitExceededError(
                        f"DOCX member compression ratio is unsafe: {info.filename}"
                    )
            members.append(
                ArchiveMember(
                    name=info.filename,
                    compressed_bytes=info.compress_size,
                    uncompressed_bytes=info.file_size,
                )
            )

        required = {"[Content_Types].xml", "word/document.xml"}
        missing = sorted(required - names)
        if missing:
            raise DocumentExtractionError(
                f"DOCX package is missing required members: {', '.join(missing)}"
            )
        lowered_names = {name.lower() for name in names}
        if "word/vbaproject.bin" in lowered_names:
            raise UnsafeDocumentError("Macro-enabled Word packages are not supported")
        if any(name.startswith("word/activex/") for name in lowered_names):
            raise UnsafeDocumentError("ActiveX content is not supported")
        return tuple(members)
