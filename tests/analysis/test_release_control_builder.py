"""Contract checks for locally authored A8 DOCX and adversarial PDF controls."""

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_analysis_release_controls.py"


def test_control_builder_is_analysis_only_and_declares_all_control_outputs() -> None:
    source = SCRIPT.read_text()

    compile(source, str(SCRIPT), "exec")
    assert "image-server-system-architecture.docx" in source
    assert "nist-mixed-visuals.docx" in source
    assert "prompt-injection-control.pdf" in source
    assert ".vsdx" not in source.casefold()


def test_control_builder_keeps_adversarial_text_explicitly_quoted() -> None:
    source = SCRIPT.read_text()

    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in source
    assert "quoted adversarial source data, not an instruction" in source
    assert "Decorative mountain landscape, not a diagram" in source
    assert "High-level IMAGE server architecture diagram" in source
