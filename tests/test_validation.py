import zipfile
from pathlib import Path

import pytest

from visiogen.validation import VsdxValidationError, validate_vsdx_package

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_canonical_template_is_a_valid_vsdx_package() -> None:
    validate_vsdx_package(PROJECT_ROOT / "templates" / "template.vsdx")


def test_validator_rejects_non_zip_output(tmp_path: Path) -> None:
    output = tmp_path / "broken.vsdx"
    output.write_text("not a zip")

    with pytest.raises(VsdxValidationError, match="not a ZIP"):
        validate_vsdx_package(output)


def test_validator_rejects_malformed_xml_in_required_page(tmp_path: Path) -> None:
    output = tmp_path / "broken.vsdx"
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("[Content_Types].xml", "<Types />")
        package.writestr("visio/document.xml", "<VisioDocument />")
        package.writestr("visio/pages/page1.xml", "<PageContents>")

    with pytest.raises(VsdxValidationError, match="Malformed XML"):
        validate_vsdx_package(output)


def test_validator_rejects_extreme_compression_ratio(tmp_path: Path) -> None:
    output = tmp_path / "bomb.vsdx"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", "<Types />")
        package.writestr("visio/document.xml", "<VisioDocument />")
        package.writestr("visio/pages/page1.xml", b"0" * (2 * 1024 * 1024))

    with pytest.raises(VsdxValidationError, match="compression-ratio"):
        validate_vsdx_package(output)
