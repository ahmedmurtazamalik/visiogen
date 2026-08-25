"""Bounded raster-header inspection without image decoding."""

import io

import pytest
from PIL import Image

from visiogen.documents.errors import (
    DocumentExtractionError,
    DocumentLimitExceededError,
)
from visiogen.documents.image import inspect_raster_dimensions
from visiogen.documents.safety import DocumentSafetyLimits


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "GIF"])
def test_raster_header_inspection_supports_every_admitted_format(
    image_format: str,
) -> None:
    stream = io.BytesIO()
    Image.new("RGB", (17, 9), "white").save(stream, format=image_format)

    dimensions = inspect_raster_dimensions(
        stream.getvalue(),
        limits=DocumentSafetyLimits(),
    )

    assert (dimensions.width, dimensions.height, dimensions.pixels) == (17, 9, 153)


def test_raster_header_inspection_rejects_malformed_and_oversized_images() -> None:
    with pytest.raises(DocumentExtractionError, match="malformed header"):
        inspect_raster_dimensions(b"not an image", limits=DocumentSafetyLimits())

    oversized_png_header = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + (100_000).to_bytes(4, "big")
        + (100_000).to_bytes(4, "big")
    )
    with pytest.raises(DocumentLimitExceededError, match="pixel limit"):
        inspect_raster_dimensions(
            oversized_png_header,
            limits=DocumentSafetyLimits(max_image_pixels=1_000_000),
        )
