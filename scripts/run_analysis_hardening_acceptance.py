#!/usr/bin/env python3
"""Run the deterministic A8 security and resource-limit acceptance gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from visiogen.documents.artifacts import publish_artifact_directory

_REPOSITORY = Path(__file__).resolve().parents[1]
_HARDENING_TESTS = {
    "pdf_active_content": [
        "tests/documents/test_pdf_extraction.py::test_extract_pdf_rejects_javascript_and_malformed_sources",
        "tests/documents/test_pdf_extraction.py::test_extract_pdf_rejects_active_external_and_encrypted_content",
        "tests/documents/test_pdf_security.py",
    ],
    "docx_container_safety": [
        "tests/documents/test_safety.py::test_docx_inventory_rejects_traversal_and_duplicate_members",
        "tests/documents/test_safety.py::test_docx_inventory_rejects_macros_and_resource_expansion",
        "tests/documents/test_safety.py::test_docx_inventory_rejects_encrypted_symlink_and_activex_members",
        "tests/documents/test_safety.py::test_docx_inventory_enforces_entry_and_expansion_limits",
    ],
    "admission_and_image_limits": [
        "tests/documents/test_sniffing.py::test_admission_rejects_symlink_and_file_size_limit",
        "tests/documents/test_image.py::test_raster_header_inspection_rejects_malformed_and_oversized_images",
        "tests/analysis/test_preparation.py::test_preparation_fails_atomically_when_tile_limit_is_exceeded",
    ],
    "prompt_injection_isolation": [
        "tests/analysis/test_claim_workflow.py::test_claim_workflow_treats_prompt_injection_as_quoted_source_data",
        "tests/analysis/test_description.py::test_markdown_escapes_source_controlled_markup",
    ],
    "artifact_and_failure_safety": [
        "tests/documents/test_artifacts.py",
        "tests/analysis/test_analysis_pipeline.py::test_pipeline_marks_one_candidate_failure_as_partial_and_keeps_success",
        "tests/analysis/test_analysis_pipeline.py::test_pipeline_retains_prior_and_failed_model_call_provenance",
        "tests/analysis/test_analysis_pipeline.py::test_pipeline_refuses_nonempty_or_symlink_artifact_directory",
        "tests/analysis/test_analysis_pipeline.py::test_pipeline_refuses_artifact_directory_that_contains_source",
        "tests/analysis/test_release_execution.py::test_bundle_verification_rejects_tampering_dirty_source_and_vsdx",
    ],
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_REPOSITORY, text=True, capture_output=True, check=True
    ).stdout.strip()


def _file_hashes() -> dict[str, str]:
    paths = {
        target.split("::", 1)[0]
        for targets in _HARDENING_TESTS.values()
        for target in targets
    }
    return {
        path: hashlib.sha256((_REPOSITORY / path).read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == _REPOSITORY or _REPOSITORY in output.parents:
        parser.error("Hardening evidence must be written outside the source checkout")
    if _git("status", "--porcelain"):
        parser.error("Hardening acceptance requires a clean immutable source checkout")
    revision = _git("rev-parse", "HEAD")

    def build(stage: Path) -> dict[str, object]:
        junit = stage / "pytest-junit.xml"
        targets = [target for group in _HARDENING_TESTS.values() for target in group]
        command = [sys.executable, "-m", "pytest", "-q", f"--junitxml={junit}", *targets]
        completed = subprocess.run(
            command,
            cwd=_REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
        )
        (stage / "pytest-stdout.txt").write_text(completed.stdout)
        (stage / "pytest-stderr.txt").write_text(completed.stderr)
        report: dict[str, object] = {
            "status": "passed" if completed.returncode == 0 else "failed",
            "source_revision": revision,
            "source_clean": True,
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version,
            "test_groups": _HARDENING_TESTS,
            "test_file_sha256": _file_hashes(),
            "pytest_returncode": completed.returncode,
        }
        (stage / "acceptance-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        return report

    report = publish_artifact_directory(output, build)
    print(f"A8 hardening acceptance: {report['status']}")
    print(f"Evidence: {output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
