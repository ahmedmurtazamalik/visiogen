"""A7 fresh-document acceptance fixture and provenance requirements."""

import json
from pathlib import Path
import subprocess
import sys

from visiogen.documents.extractor import extract_document


def _prepare(script: Path, output: Path, repository: Path) -> dict[str, object]:
    subprocess.run(
        [sys.executable, str(script), "--output", str(output), "--prepare-only"],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads((output / "acceptance-report.json").read_text())


def test_a7_runner_builds_repeatable_fresh_pdf_and_docx(tmp_path: Path) -> None:
    repository = Path(__file__).parents[2]
    script = repository / "scripts/run_analysis_vertical_acceptance.py"
    first = _prepare(script, tmp_path / "first", repository)
    second = _prepare(script, tmp_path / "second", repository)

    assert first["status"] == "prepared"
    assert first["implementation_sha256"] == second["implementation_sha256"]
    assert first["cases"] == second["cases"]
    assert {case["id"] for case in first["cases"]} == {"fresh-pdf", "fresh-docx"}

    for filename, expected_kind in (
        ("fresh-control-system.pdf", "pdf"),
        ("fresh-control-system.docx", "docx"),
    ):
        snapshot = extract_document(
            tmp_path / "first/inputs" / filename,
            tmp_path / f"snapshot-{expected_kind}",
        )
        assert snapshot.document_kind == expected_kind
        assert len(snapshot.visual_assets) == 1
        assert "The Sensor sends measurements to the Processor." in {
            block.text for block in snapshot.text_blocks
        }


def test_a7_runner_checks_complete_hash_bound_non_vsdx_bundles() -> None:
    source = (
        Path(__file__).parents[2] / "scripts/run_analysis_vertical_acceptance.py"
    ).read_text()

    assert '"bundle_sha256": _bundle_sha256(bundle)' in source
    assert 'manifest["total_model_calls"] < 4' in source
    assert 'list(bundle.rglob("*.vsdx"))' in source
    assert '"observation", "reconstruction", "claims"' in source
