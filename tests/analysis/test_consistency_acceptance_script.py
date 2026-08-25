"""A6 acceptance-runner provenance and reproducibility requirements."""

import json
from pathlib import Path
import subprocess
import sys


def test_a6_runner_records_hashes_thresholds_inputs_and_findings(tmp_path: Path) -> None:
    repository = Path(__file__).parents[2]
    script = repository / "scripts/run_analysis_consistency_corpus.py"
    source = script.read_text()
    assert '"implementation_sha256"' in source
    assert '"corpus_sha256"' in source
    assert '"confirmed_contradiction_precision"' in source
    assert '"non_exhaustive_omission_false_positives"' in source
    assert '"diagram": diagram.model_dump' in source
    assert '"analysis": analysis.model_dump' in source

    output = tmp_path / "a6.json"
    subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
    )
    report = json.loads(output.read_text())
    assert report["status"] == "passed"
    assert report["case_count"] == 39
    assert report["metrics"] == {
        "ambiguous_safety": 1.0,
        "case_accuracy": 1.0,
        "confirmed_contradiction_precision": 1.0,
        "evidence_validity": 1.0,
        "non_exhaustive_omission_false_positives": 0,
    }
