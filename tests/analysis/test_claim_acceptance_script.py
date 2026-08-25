"""Provenance requirements for the real A5 corpus runner."""

from pathlib import Path


def test_a5_runner_requires_clean_source_and_exact_quality_metrics() -> None:
    script = (Path(__file__).parents[2] / "scripts/run_analysis_claim_corpus.py").read_text()
    assert 'status", "--porcelain"' in script
    assert "clean immutable source checkout" in script
    assert '"corpus_sha256"' in script
    assert '"modality_accuracy"' in script
    assert '"ambiguous_unresolved"' in script
    assert '"exact_span_validity"' in script
