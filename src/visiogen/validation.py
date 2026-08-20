"""Generated VSDX package validation."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_PACKAGE_MEMBERS = 2_000
MAX_MEMBER_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


class VsdxValidationError(ValueError):
    """Raised when a generated file is not a structurally readable VSDX package."""


def validate_vsdx_package(path: str | Path) -> None:
    """Validate ZIP integrity, required parts, and parse every XML package part."""

    package_path = Path(path)
    if not package_path.is_file():
        raise VsdxValidationError(f"VSDX package was not found: {package_path}")
    if not zipfile.is_zipfile(package_path):
        raise VsdxValidationError("Generated output is not a ZIP-based VSDX package")

    try:
        with zipfile.ZipFile(package_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_PACKAGE_MEMBERS:
                raise VsdxValidationError("VSDX package contains too many members")
            total_uncompressed = 0
            for member in members:
                if member.flag_bits & 0x1:
                    raise VsdxValidationError("Encrypted VSDX members are not supported")
                if member.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                    raise VsdxValidationError("VSDX member exceeds the size limit")
                total_uncompressed += member.file_size
                if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise VsdxValidationError("VSDX package exceeds the expanded-size limit")
                if member.file_size and (
                    member.compress_size == 0
                    or member.file_size / member.compress_size > MAX_COMPRESSION_RATIO
                ):
                    raise VsdxValidationError("VSDX member exceeds the compression-ratio limit")

            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise VsdxValidationError(f"Corrupt VSDX member: {corrupt_member}")
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "visio/document.xml"}
            missing = sorted(required - names)
            if missing:
                raise VsdxValidationError(
                    f"VSDX package is missing required part(s): {', '.join(missing)}"
                )
            if not any(
                name.startswith("visio/pages/page") and name.endswith(".xml")
                for name in names
            ):
                raise VsdxValidationError("VSDX package contains no page XML")
            for name in sorted(names):
                if name.endswith((".xml", ".rels")):
                    try:
                        ET.fromstring(archive.read(name))
                    except ET.ParseError as error:
                        raise VsdxValidationError(
                            f"Malformed XML package part: {name}"
                        ) from error
    except zipfile.BadZipFile as error:
        raise VsdxValidationError("Generated output is not a readable VSDX package") from error
