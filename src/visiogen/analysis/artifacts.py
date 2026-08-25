"""Private, hash-bound artifact writing for the A7 analysis pipeline."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from visiogen.analysis.comparison import render_findings_markdown
from visiogen.analysis.description import render_description_markdown
from visiogen.analysis.models import AnalysisModel

if TYPE_CHECKING:
    from visiogen.analysis.pipeline import CandidateAnalysisRecord, DocumentAnalysis
    from visiogen.documents.models import DocumentSnapshot


class AnalysisArtifact(AnalysisModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)


class AnalysisManifest(AnalysisModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_byte_size: int = Field(gt=0)
    document_kind: str = Field(min_length=1)
    application_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    started_at_utc: str = Field(min_length=1)
    completed_at_utc: str = Field(min_length=1)
    total_elapsed_ms: float = Field(ge=0)
    total_model_calls: int = Field(ge=0)
    classification_elapsed_ms: float | None = Field(default=None, ge=0)
    source_revision: str | None = None
    source_worktree_clean: bool | None = None
    tools: dict[str, str]
    schema_sha256: dict[str, str]
    artifacts: list[AnalysisArtifact]
    warnings: list[str]
    partial_failures: list[str]


class RuntimeProvenance(AnalysisModel):
    source_revision: str | None = None
    source_worktree_clean: bool | None = None
    tools: dict[str, str] = Field(default_factory=dict)


def _json_bytes(value: Any) -> bytes:
    def jsonable(item: Any) -> Any:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        if isinstance(item, dict):
            return {key: jsonable(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [jsonable(child) for child in item]
        return item

    value = jsonable(value)
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _safe_path(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
        raise ValueError("Analysis artifact path must remain inside its bundle")
    path = root.joinpath(*pure.parts)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("Analysis artifact path must not be a symbolic link")
    return path


def _write_bytes(root: Path, relative: str, data: bytes) -> None:
    _safe_path(root, relative).write_bytes(data)


def _write_json(root: Path, relative: str, value: Any) -> None:
    _write_bytes(root, relative, _json_bytes(value))


def _write_text(root: Path, relative: str, value: str) -> None:
    _write_bytes(root, relative, value.encode())


def write_candidate_artifacts(root: Path, record: CandidateAnalysisRecord) -> None:
    """Persist one completed or failed candidate without hiding partial outcomes."""

    prefix = f"{record.candidate_id}"
    _write_json(root, f"{prefix}/00-result.json", record)
    if record.status == "failed":
        for failure_index, failure in enumerate(record.call_failures, start=1):
            for trace_index, trace in enumerate(failure.traces, start=1):
                trace_prefix = (
                    f"{prefix}/traces/failed-{failure_index:02d}-{trace_index:02d}"
                )
                _write_text(root, f"{trace_prefix}-system.txt", trace.system_prompt)
                _write_text(root, f"{trace_prefix}-user.txt", trace.user_prompt)
                if trace.transport_prompt is not None:
                    _write_text(
                        root,
                        f"{trace_prefix}-transport.txt",
                        trace.transport_prompt,
                    )
                _write_text(root, f"{trace_prefix}-response.json", trace.raw_response)
        return
    assert record.semantic is not None
    assert record.description is not None
    assert record.selection is not None
    assert record.claims is not None
    assert record.alignments is not None
    _write_json(root, f"{prefix}/14-validated-observations.json", record.semantic.observation.observations)
    _write_json(root, f"{prefix}/24-analyzed-diagram.json", record.semantic.reconstruction.diagram)
    _write_text(root, f"{prefix}/25-description.md", render_description_markdown(record.description))
    _write_json(root, f"{prefix}/30-selected-text-blocks.json", record.selection)
    _write_json(root, f"{prefix}/34-document-claims.json", record.claims)
    _write_json(root, f"{prefix}/40-alignments.json", record.alignments)
    if record.consistency is not None:
        _write_json(
            root,
            f"{prefix}/41-comparison-input.json",
            {
                "diagram": record.semantic.reconstruction.diagram.model_dump(mode="json"),
                "claims": record.claims.model_dump(mode="json"),
                "alignments": record.alignments.model_dump(mode="json"),
            },
        )
        if record.adjudications:
            _write_json(root, f"{prefix}/42-adjudications.json", record.adjudications)
        _write_json(root, f"{prefix}/43-findings.json", record.consistency)
        _write_text(root, f"{prefix}/44-findings.md", render_findings_markdown(record.consistency))
    for stage_name, traces in (
        ("observation", record.semantic.observation.traces),
        ("reconstruction", record.semantic.reconstruction.traces),
        ("claims", record.claim_extraction.traces if record.claim_extraction else []),
        (
            "adjudication",
            [
                trace
                for adjudication in record.adjudications
                for trace in adjudication.result.traces
            ],
        ),
        (
            "failed",
            [trace for failure in record.call_failures for trace in failure.traces],
        ),
    ):
        for index, trace in enumerate(traces, start=1):
            trace_prefix = f"{prefix}/traces/{stage_name}-{index:02d}"
            _write_text(root, f"{trace_prefix}-system.txt", trace.system_prompt)
            _write_text(root, f"{trace_prefix}-user.txt", trace.user_prompt)
            if trace.transport_prompt is not None:
                _write_text(root, f"{trace_prefix}-transport.txt", trace.transport_prompt)
            _write_text(root, f"{trace_prefix}-response.json", trace.raw_response)


def render_document_report(analysis: DocumentAnalysis) -> str:
    """Render a stable aggregate report with explicit candidate failures."""

    lines = [
        "# Visiogen document analysis",
        "",
        f"- Source: {analysis.source_name}",
        f"- Status: `{analysis.status}`",
        f"- Candidates selected: {len(analysis.candidates)}",
        "",
    ]
    for record in analysis.candidates:
        lines.extend([f"## {record.candidate_id}", ""])
        if record.status == "failed":
            lines.extend(
                [
                    f"Analysis failed during `{record.failed_stage}`: {record.error_type}: {record.error_message}",
                    "",
                ]
            )
            continue
        assert record.description is not None
        lines.append(render_description_markdown(record.description).rstrip())
        lines.append("")
        if record.consistency is not None:
            lines.append(render_findings_markdown(record.consistency).rstrip())
            lines.append("")
        if record.warnings:
            lines.extend(["### Candidate warnings", ""])
            lines.extend(f"- {warning}" for warning in record.warnings)
            lines.append("")
    if analysis.warnings:
        lines.extend(["## Analysis warnings", ""])
        lines.extend(f"- {warning}" for warning in analysis.warnings)
        lines.append("")
    return "\n".join(lines)


def _file_inventory(root: Path) -> list[AnalysisArtifact]:
    artifacts = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name == "manifest.json":
            continue
        data = path.read_bytes()
        artifacts.append(
            AnalysisArtifact(
                path=path.relative_to(root).as_posix(),
                sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data),
            )
        )
    return artifacts


def write_analysis_bundle(
    root: Path,
    snapshot: DocumentSnapshot,
    analysis: DocumentAnalysis,
    discovery: AnalysisModel,
    *,
    classification_trace: BaseModel | None,
    runtime: RuntimeProvenance,
    started_at_utc: str,
    total_elapsed_ms: float,
    application_version: str,
    provider: str,
    model: str,
    schema_models: tuple[type[AnalysisModel], ...],
) -> AnalysisManifest:
    """Write aggregate results last, then checksum every published artifact."""

    _write_json(
        root,
        "00-source-metadata.json",
        {
            "source_id": snapshot.source_id,
            "source_name": snapshot.source_name,
            "source_sha256": snapshot.source_sha256,
            "byte_size": snapshot.byte_size,
            "document_kind": snapshot.document_kind,
            "media_type": snapshot.media_type,
        },
    )
    _write_json(root, "01-document-snapshot.json", snapshot)
    _write_json(root, "03-candidates.json", discovery)
    if classification_trace is not None:
        _write_json(root, "04-classification-trace.json", classification_trace)
        _write_text(
            root,
            "05-classification-system-prompt.txt",
            classification_trace.system_prompt,
        )
        _write_text(
            root,
            "06-classification-user-prompt.txt",
            classification_trace.user_prompt,
        )
        if classification_trace.transport_prompt is not None:
            _write_text(
                root,
                "07-classification-transport-prompt.txt",
                classification_trace.transport_prompt,
            )
        _write_text(
            root,
            "08-classification-response.json",
            classification_trace.raw_response,
        )
    _write_json(root, "analysis.json", analysis)
    _write_text(root, "report.md", render_document_report(analysis))
    failures = [record.candidate_id for record in analysis.candidates if record.status == "failed"]
    manifest = AnalysisManifest(
        source_id=snapshot.source_id,
        source_name=snapshot.source_name,
        source_sha256=snapshot.source_sha256,
        source_byte_size=snapshot.byte_size,
        document_kind=snapshot.document_kind,
        application_version=application_version,
        provider=provider,
        model=model,
        started_at_utc=started_at_utc,
        completed_at_utc=datetime.now(timezone.utc).isoformat(),
        total_elapsed_ms=total_elapsed_ms,
        total_model_calls=(1 if classification_trace is not None else 0)
        + sum(record.model_calls for record in analysis.candidates),
        classification_elapsed_ms=(
            getattr(classification_trace, "elapsed_ms", None)
            if classification_trace is not None
            else None
        ),
        source_revision=runtime.source_revision,
        source_worktree_clean=runtime.source_worktree_clean,
        tools=runtime.tools,
        schema_sha256={
            item.__name__: hashlib.sha256(
                json.dumps(item.model_json_schema(), sort_keys=True).encode()
            ).hexdigest()
            for item in schema_models
        },
        artifacts=_file_inventory(root),
        warnings=analysis.warnings,
        partial_failures=failures,
    )
    _write_json(root, "manifest.json", manifest)
    return manifest
