"""A8 verification for production analysis bundles produced from real documents."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from visiogen.analysis.models import AnalysisModel
from visiogen.analysis.release_evaluation import ReleaseCase


class ExecutedCase(AnalysisModel):
    """Checksum-bound execution outcome for one admitted A8 source."""

    case_id: str = Field(min_length=1)
    status: Literal["complete", "partial", "failed"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    analysis_status: Literal["complete", "partial"] | None = None
    model_calls: int = Field(default=0, ge=0)
    failures: list[str] = Field(default_factory=list)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_directory(root: Path) -> str:
    """Hash relative names and contents so a review binds to the complete bundle."""

    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
        digest.update(b"\0")
    return digest.hexdigest()


def verify_analysis_bundle(case: ReleaseCase, bundle: Path) -> ExecutedCase:
    """Verify identity, artifact hashes, provenance, and analysis-only boundaries."""

    failures: list[str] = []
    manifest_path = bundle / "manifest.json"
    analysis_path = bundle / "analysis.json"
    if not manifest_path.is_file() or not analysis_path.is_file():
        missing = [
            name
            for name, path in (("manifest.json", manifest_path), ("analysis.json", analysis_path))
            if not path.is_file()
        ]
        return ExecutedCase(
            case_id=case.id,
            status="failed",
            source_sha256=case.source_sha256,
            bundle_sha256=sha256_directory(bundle) if bundle.is_dir() else None,
            failures=["missing required bundle artifact: " + ", ".join(missing)],
        )
    try:
        manifest = json.loads(manifest_path.read_text())
        analysis = json.loads(analysis_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return ExecutedCase(
            case_id=case.id,
            status="failed",
            source_sha256=case.source_sha256,
            bundle_sha256=sha256_directory(bundle),
            failures=[f"invalid bundle JSON: {type(error).__name__}: {error}"],
        )
    if manifest.get("source_sha256") != case.source_sha256:
        failures.append("bundle source hash does not match admitted corpus source")
    if manifest.get("document_kind") != case.document_kind:
        failures.append("bundle document kind does not match corpus declaration")
    if not manifest.get("provider") or not manifest.get("model"):
        failures.append("bundle provider/model provenance is missing")
    if not manifest.get("schema_sha256") or not manifest.get("tools"):
        failures.append("bundle schema/tool provenance is missing")
    if manifest.get("source_worktree_clean") is not True:
        failures.append("bundle was not produced from a recorded clean source checkout")
    for artifact in manifest.get("artifacts", []):
        relative = artifact.get("path", "")
        path = bundle / relative
        if not path.is_file():
            failures.append(f"missing manifest artifact: {relative}")
        elif sha256_file(path) != artifact.get("sha256"):
            failures.append(f"manifest artifact hash mismatch: {relative}")
        elif path.stat().st_size != artifact.get("byte_size"):
            failures.append(f"manifest artifact size mismatch: {relative}")
    if list(bundle.rglob("*.vsdx")):
        failures.append("analysis bundle contains a forbidden VSDX artifact")
    analysis_status = analysis.get("status")
    if analysis_status not in {"complete", "partial"}:
        failures.append("analysis status is missing or invalid")
        analysis_status = None
    model_calls = manifest.get("total_model_calls", 0)
    if not isinstance(model_calls, int) or model_calls < 0:
        failures.append("model-call provenance is invalid")
        model_calls = 0
    status = "failed" if failures else analysis_status
    return ExecutedCase(
        case_id=case.id,
        status=status or "failed",
        source_sha256=case.source_sha256,
        bundle_sha256=sha256_directory(bundle),
        analysis_status=analysis_status,
        model_calls=model_calls,
        failures=failures,
    )
