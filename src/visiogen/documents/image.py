"""Bounded raster metadata inspection without decoding untrusted pixels."""

from __future__ import annotations

from dataclasses import dataclass
import struct

from visiogen.documents.errors import DocumentExtractionError, DocumentLimitExceededError
from visiogen.documents.safety import DocumentSafetyLimits


@dataclass(frozen=True, slots=True)
class RasterDimensions:
    width: int
    height: int

    @property
    def pixels(self) -> int:
        return self.width * self.height


def _png_dimensions(data: bytes) -> RasterDimensions | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    width, height = struct.unpack(">II", data[16:24])
    return RasterDimensions(width, height)


def _gif_dimensions(data: bytes) -> RasterDimensions | None:
    if len(data) < 10 or data[:6] not in {b"GIF87a", b"GIF89a"}:
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return RasterDimensions(width, height)


def _jpeg_dimensions(data: bytes) -> RasterDimensions | None:
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            break
        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(data):
            break
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            if segment_length < 7:
                break
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return RasterDimensions(width, height)
        offset += segment_length
    return None


def inspect_raster_dimensions(
    data: bytes,
    *,
    limits: DocumentSafetyLimits,
) -> RasterDimensions:
    """Read PNG/JPEG/GIF dimensions and reject malformed or oversized images."""

    dimensions = _png_dimensions(data) or _gif_dimensions(data) or _jpeg_dimensions(data)
    if dimensions is None or dimensions.width <= 0 or dimensions.height <= 0:
        raise DocumentExtractionError("Embedded raster has an unsupported or malformed header")
    if dimensions.pixels > limits.max_image_pixels:
        raise DocumentLimitExceededError("Decoded image would exceed the pixel limit")
    return dimensions
