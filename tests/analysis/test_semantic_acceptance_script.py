"""Safety and provenance requirements for the real A3 corpus runner."""

from pathlib import Path


def test_a3_runner_requires_clean_source_metrics_and_exact_evidence() -> None:
    script = (
        Path(__file__).parents[2] / "scripts/run_analysis_semantic_corpus.py"
    ).read_text()

    assert 'status", "--porcelain"' in script
    assert "clean immutable source checkout" in script
    assert "outside the source checkout" in script
    assert '"provider_version"' in script
    assert '"corpus_sha256"' in script
    assert '"object_precision"' in script
    assert '"edge_recall"' in script
    assert '"direction_accuracy"' in script
    assert '"result": result.model_dump' in script
    assert "ObservationWorkflowError" in script
    assert 'failure["traces"]' in script
