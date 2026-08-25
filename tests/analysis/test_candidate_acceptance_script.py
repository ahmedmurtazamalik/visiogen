"""Safety and provenance requirements for the real A2 corpus runner."""

from pathlib import Path


def test_a2_corpus_runner_requires_immutable_source_and_complete_evidence() -> None:
    script = (
        Path(__file__).parents[2] / "scripts/run_analysis_candidate_corpus.py"
    ).read_text()

    assert 'status", "--porcelain"' in script
    assert "clean immutable source checkout" in script
    assert "outside the source checkout" in script
    assert '"source_revision"' in script
    assert '"corpus_sha256"' in script
    assert '"classification_trace"' in script
    assert '"image_sha256"' in script
    assert '"diagram_precision"' in script
    assert '"non_diagram_recall"' in script
