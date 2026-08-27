"""A8 production-bundle verification tests."""

import hashlib
import json
from pathlib import Path

from visiogen.analysis.release_evaluation import ReleaseCase
from visiogen.analysis.release_execution import sha256_directory, verify_analysis_bundle


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _case(source_sha: str) -> ReleaseCase:
    return ReleaseCase.model_validate(
        {
            "id": "held-pdf",
            "subset": "held_out",
            "document_kind": "pdf",
            "source_path": "sources/input.pdf",
            "source_sha256": source_sha,
            "clean_input": True,
            "coverage_tags": ["clean_native_text_pdf"],
        }
    )


def _write_bundle(root: Path, source_sha: str) -> Path:
    root.mkdir()
    analysis = (json.dumps({"status": "complete"}) + "\n").encode()
    (root / "analysis.json").write_bytes(analysis)
    artifact = {
        "path": "analysis.json",
        "sha256": _sha(analysis),
        "byte_size": len(analysis),
    }
    manifest = {
        "source_sha256": source_sha,
        "document_kind": "pdf",
        "provider": "codex-cli",
        "model": "gpt-5.6-sol",
        "schema_sha256": {"analysis": "b" * 64},
        "tools": {"python": "3.11"},
        "source_worktree_clean": True,
        "total_model_calls": 4,
        "artifacts": [artifact],
    }
    (root / "manifest.json").write_text(json.dumps(manifest) + "\n")
    return root


def test_bundle_verification_accepts_hash_bound_analysis_only_output(tmp_path) -> None:
    source_sha = "a" * 64
    bundle = _write_bundle(tmp_path / "bundle", source_sha)

    result = verify_analysis_bundle(_case(source_sha), bundle)

    assert result.status == "complete"
    assert result.analysis_status == "complete"
    assert result.model_calls == 4
    assert result.bundle_sha256 == sha256_directory(bundle)
    assert not result.failures


def test_bundle_verification_preserves_partial_status(tmp_path) -> None:
    source_sha = "a" * 64
    bundle = _write_bundle(tmp_path / "bundle", source_sha)
    (bundle / "analysis.json").write_text(json.dumps({"status": "partial"}) + "\n")
    data = (bundle / "analysis.json").read_bytes()
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["artifacts"][0].update(sha256=_sha(data), byte_size=len(data))
    (bundle / "manifest.json").write_text(json.dumps(manifest) + "\n")

    result = verify_analysis_bundle(_case(source_sha), bundle)

    assert result.status == "partial"
    assert not result.failures


def test_bundle_verification_rejects_tampering_dirty_source_and_vsdx(tmp_path) -> None:
    source_sha = "a" * 64
    bundle = _write_bundle(tmp_path / "bundle", source_sha)
    (bundle / "analysis.json").write_text('{"status":"complete","tampered":true}\n')
    (bundle / "forbidden.vsdx").write_bytes(b"not allowed")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["source_worktree_clean"] = False
    (bundle / "manifest.json").write_text(json.dumps(manifest) + "\n")

    result = verify_analysis_bundle(_case(source_sha), bundle)

    assert result.status == "failed"
    assert any("hash mismatch" in failure for failure in result.failures)
    assert any("clean source" in failure for failure in result.failures)
    assert any("forbidden VSDX" in failure for failure in result.failures)


def test_bundle_verification_reports_missing_or_invalid_core_artifacts(tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    missing = verify_analysis_bundle(_case("a" * 64), empty)
    assert missing.status == "failed"
    assert any("missing required" in failure for failure in missing.failures)

    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "manifest.json").write_text("not json")
    (invalid / "analysis.json").write_text("{}")
    malformed = verify_analysis_bundle(_case("a" * 64), invalid)
    assert malformed.status == "failed"
    assert any("invalid bundle JSON" in failure for failure in malformed.failures)
