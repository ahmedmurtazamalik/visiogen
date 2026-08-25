"""Safety and provenance requirements for the deterministic A4 corpus runner."""

from pathlib import Path


def test_a4_runner_binds_a3_evidence_clean_source_and_exact_metrics() -> None:
    script = (
        Path(__file__).parents[2] / "scripts/run_analysis_description_corpus.py"
    ).read_text()

    assert 'status", "--porcelain"' in script
    assert "clean immutable source checkout" in script
    assert "outside the source checkout" in script
    assert '"a3_report_sha256"' in script
    assert '"source_revision"' in script
    assert '"visible_label_coverage"' in script
    assert '"ambiguity_coverage"' in script
    assert "write_description_bundle" in script
