"""A8 verification for production analysis bundles produced from real documents."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from visiogen.analysis.models import AnalysisModel
from visiogen.analysis.release_evaluation import CaseReview, ReleaseCase


class ExecutedCase(AnalysisModel):
    """Checksum-bound execution outcome for one admitted A8 source."""

    case_id: str = Field(min_length=1)
    status: Literal["complete", "partial", "failed"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    analysis_status: Literal["complete", "partial"] | None = None
    model_calls: int = Field(default=0, ge=0)
    failures: list[str] = Field(default_factory=list)


class ReleaseEvidenceValidation(AnalysisModel):
    """Cross-file validation for execution, review, and hardening evidence."""

    valid: bool
    execution_revision: str | None = None
    hardening_revision: str | None = None
    provider: str | None = None
    model: str | None = None
    failures: list[str]


def validate_release_evidence(
    cases: list[ReleaseCase],
    reviews: list[CaseReview],
    execution: dict[str, object],
    hardening: dict[str, object],
) -> ReleaseEvidenceValidation:
    """Bind human reviews to passing production bundles and the same hardening revision."""

    failures: list[str] = []
    execution_revision = execution.get("source_revision")
    hardening_revision = hardening.get("source_revision")
    if execution.get("status") != "passed" or execution.get("complete_corpus") is not True:
        failures.append("execution evidence must be a passing complete-corpus run")
    if execution.get("source_clean") is not True:
        failures.append("execution evidence must record a clean source checkout")
    if hardening.get("status") != "passed" or hardening.get("source_clean") is not True:
        failures.append("hardening evidence must be a passing clean-source run")
    if not isinstance(execution_revision, str) or not execution_revision:
        failures.append("execution source revision is missing")
        execution_revision = None
    if not isinstance(hardening_revision, str) or not hardening_revision:
        failures.append("hardening source revision is missing")
        hardening_revision = None
    if execution_revision and hardening_revision and execution_revision != hardening_revision:
        failures.append("execution and hardening evidence must use the same source revision")
    case_by_id = {case.id: case for case in cases}
    executed_by_id: dict[str, dict[str, object]] = {}
    raw_executed = execution.get("cases", [])
    if not isinstance(raw_executed, list):
        failures.append("execution case records are invalid")
        raw_executed = []
    for item in raw_executed:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            failures.append("execution contains an invalid case record")
            continue
        case_id = item["case_id"]
        if case_id in executed_by_id:
            failures.append(f"execution case is duplicated: {case_id}")
        executed_by_id[case_id] = item
    if set(executed_by_id) != set(case_by_id):
        failures.append("execution cases do not exactly match the admitted corpus")
    for case_id, item in executed_by_id.items():
        case = case_by_id.get(case_id)
        if case is None:
            continue
        if item.get("status") != "complete":
            failures.append(f"execution case is not complete: {case_id}")
        if item.get("source_sha256") != case.source_sha256:
            failures.append(f"execution source hash mismatch: {case_id}")
        if not item.get("bundle_sha256"):
            failures.append(f"execution bundle hash is missing: {case_id}")
    review_by_id = {review.case_id: review for review in reviews}
    for case in cases:
        if case.subset != "held_out":
            continue
        review = review_by_id.get(case.id)
        executed = executed_by_id.get(case.id)
        if review is not None and executed is not None:
            if review.analysis_bundle_sha256 != executed.get("bundle_sha256"):
                failures.append(f"review bundle hash mismatch: {case.id}")
    provider = execution.get("provider")
    model = execution.get("model")
    if not isinstance(provider, str) or not provider:
        failures.append("execution provider identity is missing")
        provider = None
    if not isinstance(model, str) or not model:
        failures.append("execution model identity is missing")
        model = None
    return ReleaseEvidenceValidation(
        valid=not failures,
        execution_revision=execution_revision,
        hardening_revision=hardening_revision,
        provider=provider,
        model=model,
        failures=failures,
    )


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
