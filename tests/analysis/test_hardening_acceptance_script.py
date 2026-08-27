"""Contract coverage for the deterministic A8 hardening gate."""

from pathlib import Path
import runpy


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "scripts" / "run_analysis_hardening_acceptance.py"


def test_hardening_runner_covers_required_threat_classes_and_existing_tests() -> None:
    namespace = runpy.run_path(str(SCRIPT), run_name="hardening_contract")
    groups = namespace["_HARDENING_TESTS"]

    assert set(groups) == {
        "pdf_active_content",
        "docx_container_safety",
        "admission_and_image_limits",
        "prompt_injection_isolation",
        "artifact_and_failure_safety",
    }
    targets = [target for items in groups.values() for target in items]
    assert len(targets) == len(set(targets))
    for target in targets:
        assert (REPOSITORY / target.split("::", 1)[0]).is_file()


def test_hardening_runner_requires_clean_source_and_checksum_bound_evidence() -> None:
    source = SCRIPT.read_text()

    assert '"status", "--porcelain"' in source
    assert '"rev-parse", "HEAD"' in source
    assert "test_file_sha256" in source
    assert "pytest-junit.xml" in source
    assert "publish_artifact_directory" in source
