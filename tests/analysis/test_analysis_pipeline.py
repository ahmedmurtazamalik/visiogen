"""A7 pipeline composition, artifacts, and partial-failure behavior."""

import hashlib
from pathlib import Path

import pytest

from visiogen.analysis.adjudication import AdjudicationDecision, AdjudicationResult
from visiogen.analysis.artifacts import RuntimeProvenance
from visiogen.analysis.claim_workflow import (
    ClaimCallTrace,
    ClaimExtractionResult,
    ClaimExtractionWorkflowError,
)
from visiogen.analysis.claims import DocumentClaimBatch
from visiogen.analysis.classification import CandidateClassificationTrace
from visiogen.analysis.models import (
    CandidateCoverage,
    CandidateDecision,
    CandidateDiscovery,
    CandidatePreparation,
    DiagramCandidate,
    PreparedCandidate,
    PreparedDerivative,
)
from visiogen.analysis.observation import ObservationResult
from visiogen.analysis.pipeline import AnalysisPipelineOptions, DocumentAnalysisPipeline
from visiogen.analysis.production import build_codex_analysis_pipeline
from visiogen.analysis.reconstruction import ReconstructionResult
from visiogen.analysis.semantic_pipeline import SemanticAnalysisResult
from visiogen.analysis.semantics import AnalyzedDiagram, ValidatedObservationSet
from visiogen.config import Settings
from visiogen.documents.errors import UnsafeDocumentError
from visiogen.documents.models import (
    CoverageReport,
    DocumentSnapshot,
    NormalizedBox,
    SourceLocation,
    TextBlock,
    VisualAsset,
)


def _snapshot(root: Path, count: int = 1) -> DocumentSnapshot:
    assets = []
    assets_dir = root / "assets"
    assets_dir.mkdir(parents=True)
    for index in range(1, count + 1):
        data = f"image-{index}".encode()
        name = f"image-{index}.png"
        (assets_dir / name).write_bytes(data)
        assets.append(
            VisualAsset(
                id=f"asset-{index:04d}",
                media_type="image/png",
                origin="embedded",
                sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data),
                artifact_path=f"assets/{name}",
                width_px=100,
                height_px=100,
                location=SourceLocation(page_number=index, asset_id=f"asset-{index:04d}"),
            )
        )
    return DocumentSnapshot(
        source_id="source-1",
        source_sha256="a" * 64,
        source_name="design.pdf",
        document_kind="pdf",
        media_type="application/pdf",
        byte_size=100,
        page_count=count,
        text_blocks=[
            TextBlock(
                id="text-0001",
                text="Sensor exists in the diagram.",
                origin="native",
                order=0,
                location=SourceLocation(page_number=1, asset_id="asset-0001"),
            )
        ],
        visual_assets=assets,
        coverage=CoverageReport(
            native_text="complete",
            embedded_media="complete",
            rendered_pages="complete",
        ),
    )


def _discovery(
    snapshot: DocumentSnapshot,
    _snapshot_dir: Path,
    _options: AnalysisPipelineOptions,
) -> CandidateDiscovery:
    candidates = []
    for index, asset in enumerate(snapshot.visual_assets, start=1):
        candidate_id = f"candidate-{index:04d}"
        candidates.append(
            DiagramCandidate(
                id=candidate_id,
                primary_asset_id=asset.id,
                source_asset_ids=[asset.id],
                page_number=index,
                width_px=100,
                height_px=100,
                decision=CandidateDecision(
                    candidate_id=candidate_id,
                    label="diagram",
                    confidence="high",
                    reason="Controlled fixture",
                    classifier="fake",
                ),
                disposition="selected",
                disposition_reason="Controlled fixture",
            )
        )
    return CandidateDiscovery(
        source_id=snapshot.source_id,
        candidates=candidates,
        coverage=CandidateCoverage(
            source_assets=len(candidates),
            unique_candidates=len(candidates),
            duplicate_assets_grouped=0,
            selected=len(candidates),
            ignored_non_diagram=0,
            awaiting_classification=0,
            filtered_out=0,
            skipped_limit=0,
        ),
    )


def _prepare(snapshot, discovery, snapshot_dir, output_dir) -> CandidatePreparation:
    del snapshot, snapshot_dir
    output = Path(output_dir)
    (output / "assets").mkdir(parents=True)
    prepared = []
    region = NormalizedBox(left=0, top=0, right=1, bottom=1)
    for candidate in discovery.candidates:
        derivatives = []
        for kind in ("crop", "overview"):
            name = f"{candidate.id}-{kind}.png"
            data = f"{candidate.id}-{kind}".encode()
            (output / "assets" / name).write_bytes(data)
            derivatives.append(
                PreparedDerivative(
                    id=f"{candidate.id}-{kind}",
                    kind=kind,
                    artifact_path=f"assets/{name}",
                    sha256=hashlib.sha256(data).hexdigest(),
                    byte_size=len(data),
                    width_px=100,
                    height_px=100,
                    source_region=region,
                )
            )
        prepared.append(PreparedCandidate(candidate_id=candidate.id, derivatives=derivatives))
    return CandidatePreparation(discovery=discovery, prepared_candidates=prepared)


class FakeSemantic:
    def __init__(self, fail_candidate: str | None = None) -> None:
        self.fail_candidate = fail_candidate

    def analyze(self, prepared, bundle_dir):
        assert Path(bundle_dir).is_dir()
        if prepared.candidate_id == self.fail_candidate:
            raise RuntimeError("controlled semantic failure")
        observations = ValidatedObservationSet(
            candidate_id=prepared.candidate_id,
            evidence=[],
            observations=[],
        )
        diagram = AnalyzedDiagram.model_validate(
            {
                "candidate_id": prepared.candidate_id,
                "family": "system_block",
                "orientation": "left_to_right",
                "objects": [
                    {
                        "id": "object-0001",
                        "visible_label": "Sensor",
                        "normalized_label": "sensor",
                        "semantic_type": "component",
                        "visual_shape": "rectangle",
                        "bbox": {"left": 0.1, "top": 0.1, "right": 0.3, "bottom": 0.3},
                        "evidence_ids": ["evidence-0001"],
                        "confidence": "high",
                    }
                ],
                "relationships": [],
                "confidence": "high",
            }
        )
        return SemanticAnalysisResult(
            observation=ObservationResult(observations=observations, attempts=1, traces=[]),
            reconstruction=ReconstructionResult(diagram=diagram, attempts=1, traces=[]),
            total_model_calls=2,
        )


class FakeClaims:
    def extract(self, selection):
        text = selection.blocks[0].text
        claims = DocumentClaimBatch.model_validate(
            {
                "candidate_id": selection.candidate_id,
                "evidence": [
                    {
                        "id": "text-evidence-0001",
                        "block_id": selection.blocks[0].block_id,
                        "exact_text": text,
                        "start": 0,
                        "end": len(text),
                    }
                ],
                "claims": [
                    {
                        "id": "claim-0001",
                        "subject_text": "Sensor",
                        "normalized_subject": "sensor",
                        "predicate": "exists",
                        "modality": "asserted",
                        "scope": "current_figure",
                        "refers_to_candidate": "yes",
                        "evidence_ids": ["text-evidence-0001"],
                        "confidence": "high",
                    }
                ],
            }
        )
        return ClaimExtractionResult(claims=claims, attempts=1, traces=[])


class FakeTerminologyClaims:
    def extract(self, selection):
        text = selection.blocks[0].text
        claims = DocumentClaimBatch.model_validate(
            {
                "candidate_id": selection.candidate_id,
                "evidence": [
                    {
                        "id": "text-evidence-0001",
                        "block_id": selection.blocks[0].block_id,
                        "exact_text": text,
                        "start": 0,
                        "end": len(text),
                    }
                ],
                "claims": [
                    {
                        "id": "claim-0001",
                        "subject_text": "Sensor",
                        "normalized_subject": "sensor",
                        "predicate": "type_or_role",
                        "object_text": "detector",
                        "normalized_object": "detector",
                        "modality": "asserted",
                        "scope": "current_figure",
                        "refers_to_candidate": "yes",
                        "evidence_ids": ["text-evidence-0001"],
                        "confidence": "high",
                    }
                ],
            }
        )
        return ClaimExtractionResult(claims=claims, attempts=1, traces=[])


class TimeoutThenSuccessfulClaims(FakeClaims):
    def extract(self, selection):
        result = super().extract(selection)
        traces = [
            ClaimCallTrace(
                system_prompt="claim system",
                user_prompt="claim request",
                transport_prompt="isolated",
                raw_response="",
                elapsed_ms=25,
                error_type="ProviderTimeoutError",
                error_message="temporary timeout",
            ),
            ClaimCallTrace(
                system_prompt="claim system",
                user_prompt="claim request",
                transport_prompt="isolated",
                raw_response=result.claims.model_dump_json(),
                elapsed_ms=5,
            ),
        ]
        return result.model_copy(update={"attempts": 2, "traces": traces})


class FailingClaims:
    def extract(self, selection):
        del selection
        traces = [
            ClaimCallTrace(
                system_prompt="claim system",
                user_prompt=f"claim attempt {index}",
                transport_prompt="isolated",
                raw_response="{}",
                elapsed_ms=1,
            )
            for index in (1, 2)
        ]
        raise ClaimExtractionWorkflowError(
            "controlled claim failure",
            traces=traces,
            validation_error="missing claims",
        )


class FakeAdjudicator:
    def adjudicate(self, request):
        return AdjudicationResult(
            decision=AdjudicationDecision(
                finding_id=request.finding_id,
                status="confirmed_consistent",
                explanation="Component and detector are equivalent in the controlled domain.",
                confidence="medium",
                review_action="Confirm the domain terminology.",
            ),
            attempts=1,
            traces=[],
        )


def _pipeline(
    tmp_path: Path,
    *,
    count: int = 1,
    fail_candidate: str | None = None,
    claims=None,
    adjudicator=None,
):
    def extract(_source, output):
        return _snapshot(Path(output), count)

    class FakeDiscovery:
        last_trace = CandidateClassificationTrace(
            classifier_identity="fake:fixture",
            system_prompt="classify safely",
            user_prompt="candidate inventory",
            transport_prompt="isolated transport",
            raw_response='{"decisions": []}',
            elapsed_ms=1,
            image_sha256={"candidate-0001": "b" * 64},
        )

        def __call__(self, snapshot, snapshot_dir, options):
            return _discovery(snapshot, snapshot_dir, options)

    return DocumentAnalysisPipeline(
        extract=extract,
        discover=FakeDiscovery(),
        prepare=_prepare,
        semantic=FakeSemantic(fail_candidate),
        claims=claims or FakeClaims(),
        adjudicator=adjudicator,
        provenance=lambda: RuntimeProvenance(
            source_revision="c" * 40,
            source_worktree_clean=True,
            tools={"python": "3.11", "codex": "fixture"},
        ),
        provider="fake",
        model="fixture",
        application_version="0.1.0",
    )


def test_pipeline_composes_all_stages_and_publishes_hash_manifest(tmp_path: Path) -> None:
    artifacts = tmp_path / "evidence"

    result = _pipeline(tmp_path).analyze(tmp_path / "input.pdf", artifacts)

    assert result.analysis.status == "complete"
    assert result.analysis.candidates[0].consistency is not None
    assert (artifacts / "candidate-0001/25-description.md").is_file()
    assert (artifacts / "candidate-0001/43-findings.json").is_file()
    assert (artifacts / "04-classification-trace.json").is_file()
    assert (artifacts / "07-classification-transport-prompt.txt").is_file()
    assert (artifacts / "analysis.json").is_file()
    assert (artifacts / "report.md").is_file()
    assert result.manifest.artifacts
    assert all(len(item.sha256) == 64 for item in result.manifest.artifacts)
    assert result.manifest.source_revision == "c" * 40
    assert result.manifest.source_worktree_clean is True
    assert result.manifest.tools["codex"] == "fixture"
    assert result.manifest.total_elapsed_ms >= 0
    assert result.manifest.started_at_utc.endswith("+00:00")
    assert result.manifest.completed_at_utc.endswith("+00:00")
    assert result.manifest.total_model_calls == 4
    assert result.manifest.classification_elapsed_ms == 1


def test_pipeline_reports_stage_and_candidate_progress(tmp_path: Path) -> None:
    events = []

    _pipeline(tmp_path).analyze(
        tmp_path / "input.pdf",
        tmp_path / "evidence",
        progress=events.append,
    )

    stages = [event.stage for event in events]
    assert stages == [
        "analysis_start",
        "document_extraction",
        "diagram_discovery",
        "candidate_preparation",
        "candidate_start",
        "semantic_analysis",
        "description",
        "text_selection",
        "claim_extraction",
        "entity_alignment",
        "consistency_analysis",
        "candidate_complete",
        "artifact_publication",
        "analysis_complete",
    ]
    candidate = next(event for event in events if event.stage == "candidate_start")
    assert candidate.candidate_id == "candidate-0001"
    assert candidate.candidate_index == 1
    assert candidate.candidate_total == 1


def test_pipeline_publishes_timeout_attempt_error_metadata(tmp_path: Path) -> None:
    artifacts = tmp_path / "evidence"

    result = _pipeline(tmp_path, claims=TimeoutThenSuccessfulClaims()).analyze(
        tmp_path / "input.pdf",
        artifacts,
    )

    candidate = result.analysis.candidates[0]
    assert candidate.status == "completed"
    assert candidate.model_calls == 4
    error_path = artifacts / "candidate-0001/traces/claims-01-error.json"
    assert error_path.read_text() == (
        '{\n  "error_message": "temporary timeout",\n'
        '  "error_type": "ProviderTimeoutError"\n}\n'
    )
    assert (artifacts / "candidate-0001/traces/claims-02-response.json").is_file()


def test_pipeline_marks_one_candidate_failure_as_partial_and_keeps_success(tmp_path: Path) -> None:
    artifacts = tmp_path / "evidence"

    result = _pipeline(tmp_path, count=2, fail_candidate="candidate-0002").analyze(
        tmp_path / "input.pdf",
        artifacts,
    )

    assert result.analysis.status == "partial"
    assert [item.status for item in result.analysis.candidates] == ["completed", "failed"]
    assert result.analysis.candidates[1].failed_stage == "semantic_analysis"
    assert result.analysis.candidates[1].elapsed_ms > 0
    assert result.manifest.partial_failures == ["candidate-0002"]
    report = (artifacts / "report.md").read_text()
    assert "controlled semantic failure" in report
    assert "Sensor" in report


def test_pipeline_retains_prior_and_failed_model_call_provenance(tmp_path: Path) -> None:
    artifacts = tmp_path / "evidence"

    result = _pipeline(tmp_path, claims=FailingClaims()).analyze(
        tmp_path / "input.pdf",
        artifacts,
    )

    candidate = result.analysis.candidates[0]
    assert candidate.status == "failed"
    assert candidate.failed_stage == "claim_extraction"
    assert candidate.model_calls == 4
    assert len(candidate.call_failures) == 1
    assert candidate.call_failures[0].validation_error == "missing claims"
    assert len(candidate.call_failures[0].traces) == 2
    assert result.manifest.total_model_calls == 5
    assert len(list((artifacts / "candidate-0001/traces").glob("*-response.json"))) == 2


def test_pipeline_can_skip_consistency_without_skipping_description(tmp_path: Path) -> None:
    result = _pipeline(tmp_path).analyze(
        tmp_path / "input.pdf",
        tmp_path / "evidence",
        options=AnalysisPipelineOptions(consistency_check=False),
    )

    candidate = result.analysis.candidates[0]
    assert candidate.description is not None
    assert candidate.consistency is None


def test_pipeline_adjudicates_only_bounded_semantic_findings_and_preserves_trace(tmp_path: Path) -> None:
    artifacts = tmp_path / "evidence"
    result = _pipeline(
        tmp_path,
        claims=FakeTerminologyClaims(),
        adjudicator=FakeAdjudicator(),
    ).analyze(tmp_path / "input.pdf", artifacts)

    candidate = result.analysis.candidates[0]
    assert len(candidate.adjudications) == 1
    assert candidate.model_calls == 4
    assert candidate.consistency is not None
    terminology = next(
        item for item in candidate.consistency.findings if item.category == "terminology"
    )
    assert terminology.status == "confirmed_consistent"
    assert (artifacts / "candidate-0001/42-adjudications.json").is_file()


def test_pipeline_refuses_nonempty_or_symlink_artifact_directory(tmp_path: Path) -> None:
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "owned.txt").write_text("keep")
    with pytest.raises(UnsafeDocumentError):
        _pipeline(tmp_path).analyze(tmp_path / "input.pdf", nonempty)

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(UnsafeDocumentError):
        _pipeline(tmp_path).analyze(tmp_path / "input.pdf", link)


def test_pipeline_refuses_artifact_directory_that_contains_source(tmp_path: Path) -> None:
    source_root = tmp_path / "source-root"
    source_root.mkdir()
    source = source_root / "input.pdf"
    source.write_bytes(b"pdf")

    with pytest.raises(UnsafeDocumentError, match="contain the source"):
        _pipeline(tmp_path).analyze(source, source_root)


def test_production_factory_requires_codex_and_constructs_all_real_stage_boundaries() -> None:
    pipeline = build_codex_analysis_pipeline(
        Settings(provider="codex", codex_model="gpt-5.6-sol")
    )

    assert isinstance(pipeline, DocumentAnalysisPipeline)
    with pytest.raises(ValueError, match="requires Codex"):
        build_codex_analysis_pipeline(Settings(provider="local"))


def test_pipeline_options_reject_conflicting_candidate_scope() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        AnalysisPipelineOptions(page_number=1, candidate_id="candidate-0001")
