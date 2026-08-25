"""A7 orchestration for the provider-independent document-analysis vertical slice."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Literal, Protocol

from pydantic import Field, model_validator

from visiogen.analysis.alignment import align_claim_entities
from visiogen.analysis.adjudication import (
    AdjudicationRequest,
    AdjudicationResult,
    StructuredAdjudicationWorkflow,
    apply_adjudication_decision,
    build_adjudication_request,
)
from visiogen.analysis.artifacts import (
    AnalysisManifest,
    RuntimeProvenance,
    write_analysis_bundle,
    write_candidate_artifacts,
)
from visiogen.analysis.claim_workflow import ClaimExtractionResult
from visiogen.analysis.claims import DocumentClaimBatch, EntityAlignmentSet, TextSelection
from visiogen.analysis.comparison import ConsistencyAnalysis, compare_diagram_and_claims
from visiogen.analysis.description import DiagramDescription, compose_diagram_description
from visiogen.analysis.models import (
    AnalysisModel,
    CandidateDiscovery,
    CandidatePreparation,
    PreparedCandidate,
)
from visiogen.analysis.semantic_pipeline import SemanticAnalysisResult
from visiogen.analysis.text_selection import select_relevant_text
from visiogen.documents.artifacts import publish_artifact_directory
from visiogen.documents.errors import UnsafeDocumentError
from visiogen.documents.models import DocumentSnapshot

AnalysisStatus = Literal["complete", "partial"]
CandidateStatus = Literal["completed", "failed"]


class CandidateStageError(RuntimeError):
    def __init__(self, stage: str, error: Exception) -> None:
        self.stage = stage
        self.original = error
        super().__init__(str(error) or f"{stage} failed")


def _run_candidate_stage(stage: str, operation):
    try:
        return operation()
    except Exception as error:
        raise CandidateStageError(stage, error) from error


class CandidateAdjudication(AnalysisModel):
    request: AdjudicationRequest
    result: AdjudicationResult


class CandidateAnalysisRecord(AnalysisModel):
    candidate_id: str = Field(min_length=1)
    status: CandidateStatus
    semantic: SemanticAnalysisResult | None = None
    description: DiagramDescription | None = None
    selection: TextSelection | None = None
    claim_extraction: ClaimExtractionResult | None = None
    claims: DocumentClaimBatch | None = None
    alignments: EntityAlignmentSet | None = None
    consistency: ConsistencyAnalysis | None = None
    adjudications: list[CandidateAdjudication] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_calls: int = Field(default=0, ge=0)
    elapsed_ms: float = Field(default=0, ge=0)
    failed_stage: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> CandidateAnalysisRecord:
        completed = (self.semantic, self.description, self.selection, self.claims, self.alignments)
        if self.status == "completed" and any(item is None for item in completed):
            raise ValueError("Completed candidates require every core analysis result")
        if self.status == "completed" and any(
            item is not None for item in (self.failed_stage, self.error_type, self.error_message)
        ):
            raise ValueError("Completed candidates cannot include failure details")
        if self.status == "failed" and not all(
            (self.failed_stage, self.error_type, self.error_message)
        ):
            raise ValueError("Failed candidates require explicit failure details")
        return self


class DocumentAnalysis(AnalysisModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    status: AnalysisStatus
    candidates: list[CandidateAnalysisRecord]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_aggregate_status(self) -> DocumentAnalysis:
        failed = any(item.status == "failed" for item in self.candidates)
        if failed != (self.status == "partial"):
            raise ValueError("Document status must expose candidate failures")
        ids = [item.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Candidate analysis records must be unique")
        return self


class DocumentAnalysisResult(AnalysisModel):
    analysis: DocumentAnalysis
    manifest: AnalysisManifest
    artifact_dir: Path


class DiscoveryStage(Protocol):
    def __call__(
        self,
        snapshot: DocumentSnapshot,
        snapshot_dir: Path,
        options: AnalysisPipelineOptions,
    ) -> CandidateDiscovery: ...


class PreparationStage(Protocol):
    def __call__(
        self,
        snapshot: DocumentSnapshot,
        discovery: CandidateDiscovery,
        snapshot_dir: Path,
        output_dir: Path,
    ) -> CandidatePreparation: ...


class SemanticStage(Protocol):
    def analyze(
        self,
        prepared: PreparedCandidate,
        bundle_dir: str | Path,
    ) -> SemanticAnalysisResult: ...


class ClaimStage(Protocol):
    def extract(self, selection: TextSelection) -> ClaimExtractionResult: ...


class AdjudicationStage(Protocol):
    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationResult: ...


DocumentExtractor = Callable[[str | Path, str | Path], DocumentSnapshot]
ProvenanceProvider = Callable[[], RuntimeProvenance]


@dataclass(frozen=True, slots=True)
class AnalysisPipelineOptions:
    strict_coverage: bool = False
    consistency_check: bool = True
    page_number: int | None = None
    candidate_id: str | None = None
    max_diagrams: int = 8
    semantic_adjudication: bool = True
    max_adjudications: int = 4

    def __post_init__(self) -> None:
        if self.page_number is not None and self.page_number <= 0:
            raise ValueError("page_number must be positive")
        if self.max_diagrams <= 0:
            raise ValueError("max_diagrams must be positive")
        if self.max_adjudications <= 0:
            raise ValueError("max_adjudications must be positive")


class DocumentAnalysisPipeline:
    """Compose A1–A6 while isolating failure to an individual diagram candidate."""

    def __init__(
        self,
        *,
        extract: DocumentExtractor,
        discover: DiscoveryStage,
        prepare: PreparationStage,
        semantic: SemanticStage,
        claims: ClaimStage,
        adjudicator: AdjudicationStage | None = None,
        provenance: ProvenanceProvider = RuntimeProvenance,
        provider: str,
        model: str,
        application_version: str,
        schema_models: tuple[type[AnalysisModel], ...] = (),
    ) -> None:
        self._extract = extract
        self._discover = discover
        self._prepare = prepare
        self._semantic = semantic
        self._claims = claims
        self._adjudicator = adjudicator
        self._provenance = provenance
        self._provider = provider
        self._model = model
        self._application_version = application_version
        self._schema_models = schema_models

    def _analyze_candidate(
        self,
        prepared: PreparedCandidate,
        preparation_dir: Path,
        snapshot: DocumentSnapshot,
        discovery: CandidateDiscovery,
        options: AnalysisPipelineOptions,
    ) -> CandidateAnalysisRecord:
        started = monotonic()
        semantic = _run_candidate_stage(
            "semantic_analysis",
            lambda: self._semantic.analyze(prepared, preparation_dir),
        )
        diagram = semantic.reconstruction.diagram
        description = _run_candidate_stage(
            "description",
            lambda: compose_diagram_description(diagram),
        )
        candidate = _run_candidate_stage(
            "candidate_lookup",
            lambda: next(
                item for item in discovery.candidates if item.id == prepared.candidate_id
            ),
        )
        selection = _run_candidate_stage(
            "text_selection",
            lambda: select_relevant_text(
                snapshot,
                diagram,
                candidate_asset_ids=set(candidate.source_asset_ids),
                candidate_page_numbers=(
                    {candidate.page_number} if candidate.page_number else set()
                ),
                candidate_region=candidate.decision.region,
            ),
        )
        claim_extraction = (
            _run_candidate_stage("claim_extraction", lambda: self._claims.extract(selection))
            if selection.blocks
            else None
        )
        claims = (
            claim_extraction.claims
            if claim_extraction is not None
            else DocumentClaimBatch(candidate_id=prepared.candidate_id, evidence=[], claims=[])
        )
        alignments = _run_candidate_stage(
            "entity_alignment",
            lambda: align_claim_entities(claims, diagram),
        )
        consistency = (
            _run_candidate_stage(
                "consistency_analysis",
                lambda: compare_diagram_and_claims(
                    diagram,
                    claims,
                    alignments,
                    strict_coverage=options.strict_coverage,
                ),
            )
            if options.consistency_check
            else None
        )
        adjudications: list[CandidateAdjudication] = []
        warnings: list[str] = []
        if (
            consistency is not None
            and options.semantic_adjudication
            and self._adjudicator is not None
        ):
            updated = list(consistency.findings)
            eligible = [
                (index, finding)
                for index, finding in enumerate(updated)
                if finding.status
                in {"terminology_difference", "unverifiable", "needs_human_review"}
                and finding.category in {"alias", "terminology", "unsupported_claim"}
                and finding.diagram_evidence_ids
                and finding.text_evidence_ids
            ][: options.max_adjudications]
            for index, finding in eligible:
                request = build_adjudication_request(finding, diagram, claims)
                try:
                    adjudication = self._adjudicator.adjudicate(request)
                    updated[index] = apply_adjudication_decision(
                        finding,
                        adjudication.decision,
                    )
                    adjudications.append(
                        CandidateAdjudication(request=request, result=adjudication)
                    )
                except Exception as error:
                    warnings.append(
                        f"Semantic adjudication for {finding.id} failed: "
                        f"{type(error).__name__}: {error}"
                    )
            consistency = consistency.model_copy(update={"findings": updated})
        model_calls = semantic.total_model_calls
        if claim_extraction is not None:
            model_calls += claim_extraction.attempts
        model_calls += sum(item.result.attempts for item in adjudications)
        return CandidateAnalysisRecord(
            candidate_id=prepared.candidate_id,
            status="completed",
            semantic=semantic,
            description=description,
            selection=selection,
            claim_extraction=claim_extraction,
            claims=claims,
            alignments=alignments,
            consistency=consistency,
            adjudications=adjudications,
            warnings=warnings,
            model_calls=model_calls,
            elapsed_ms=(monotonic() - started) * 1000,
        )

    def analyze(
        self,
        source: str | Path,
        artifact_dir: str | Path,
        *,
        options: AnalysisPipelineOptions = AnalysisPipelineOptions(),
    ) -> DocumentAnalysisResult:
        """Run one document atomically while retaining explicit per-candidate failures."""

        destination = Path(artifact_dir)
        analysis_started = monotonic()
        started_at_utc = datetime.now(timezone.utc).isoformat()
        runtime = self._provenance()
        source_path = Path(source).resolve()
        destination_path = destination.resolve()
        if source_path == destination_path or source_path.is_relative_to(destination_path):
            raise UnsafeDocumentError("Artifact directory must not contain the source document")

        def build(stage: Path) -> tuple[DocumentAnalysis, AnalysisManifest]:
            snapshot_dir = stage / "document"
            snapshot = self._extract(source, snapshot_dir)
            discovery = self._discover(snapshot, snapshot_dir, options)
            classification_trace = getattr(self._discover, "last_trace", None)
            preparation_dir = stage / "prepared"
            preparation = self._prepare(
                snapshot,
                discovery,
                snapshot_dir,
                preparation_dir,
            )
            records: list[CandidateAnalysisRecord] = []
            warnings = [item.message for item in snapshot.warnings]
            if not preparation.prepared_candidates:
                warnings.append("No diagram candidates were selected for analysis")
            for prepared in preparation.prepared_candidates:
                candidate_started = monotonic()
                try:
                    record = self._analyze_candidate(
                        prepared,
                        preparation_dir,
                        snapshot,
                        discovery,
                        options,
                    )
                except Exception as error:
                    original = error.original if isinstance(error, CandidateStageError) else error
                    record = CandidateAnalysisRecord(
                        candidate_id=prepared.candidate_id,
                        status="failed",
                        failed_stage=(
                            error.stage
                            if isinstance(error, CandidateStageError)
                            else "candidate_analysis"
                        ),
                        error_type=type(original).__name__,
                        error_message=str(original) or "Candidate analysis failed",
                        elapsed_ms=(monotonic() - candidate_started) * 1000,
                    )
                records.append(record)
                write_candidate_artifacts(stage, record)
            analysis = DocumentAnalysis(
                source_id=snapshot.source_id,
                source_name=snapshot.source_name,
                status="partial" if any(item.status == "failed" for item in records) else "complete",
                candidates=records,
                warnings=warnings,
            )
            manifest = write_analysis_bundle(
                stage,
                snapshot,
                analysis,
                discovery,
                classification_trace=classification_trace,
                runtime=runtime,
                started_at_utc=started_at_utc,
                total_elapsed_ms=(monotonic() - analysis_started) * 1000,
                application_version=self._application_version,
                provider=self._provider,
                model=self._model,
                schema_models=(
                    DocumentAnalysis,
                    CandidateDiscovery,
                    CandidatePreparation,
                    DocumentClaimBatch,
                    ConsistencyAnalysis,
                    *self._schema_models,
                ),
            )
            return analysis, manifest

        analysis, manifest = publish_artifact_directory(destination, build)
        return DocumentAnalysisResult(
            analysis=analysis,
            manifest=manifest,
            artifact_dir=destination_path,
        )
