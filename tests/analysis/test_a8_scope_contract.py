"""Prevent A8 documentation from silently expanding DOCX or provider support."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCOPE = ROOT / "docs" / "analysis" / "A8_SUPPORTED_SCOPE.md"


def test_a8_scope_keeps_rendered_docx_modes_unaccepted() -> None:
    text = " ".join(SCOPE.read_text().split())

    assert "DOCX portable mode" in text
    assert "does not launch Microsoft Word or LibreOffice" in text
    assert "not accepted runtime capabilities" in text
    for unsupported in ("Word shapes", "SmartArt", "charts", "text boxes", "OLE objects"):
        assert unsupported in text


def test_a8_scope_requires_exact_release_identity_and_rerun_on_change() -> None:
    text = " ".join(SCOPE.read_text().split())

    assert "No provider/model pair is globally approved" in text
    assert "bundle SHA-256" in text
    assert "same clean source revision" in text
    assert "requires a new execution and release decision" in text
