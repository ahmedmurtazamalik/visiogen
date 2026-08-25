"""Production Codex construction for the document-analysis pipeline."""

from __future__ import annotations

from dataclasses import replace
import platform
from pathlib import Path
import shutil
import subprocess

from visiogen.analysis.classification import (
    CandidateClassificationTrace,
    StructuredCandidateClassifier,
    VisualCandidateBatch,
)
from visiogen.analysis.adjudication import (
    AdjudicationDecision,
    StructuredAdjudicationWorkflow,
)
from visiogen.analysis.artifacts import RuntimeProvenance
from visiogen.analysis.claim_workflow import StructuredClaimExtractionWorkflow
from visiogen.analysis.claims import DocumentClaimBatch
from visiogen.analysis.models import CandidateDiscovery, DiagramCandidate
from visiogen.analysis.observation import StructuredObservationWorkflow
from visiogen.analysis.pipeline import (
    AnalysisPipelineOptions,
    DocumentAnalysisPipeline,
)
from visiogen.analysis.preparation import prepare_diagram_candidates
from visiogen.analysis.reconstruction import StructuredReconstructionWorkflow
from visiogen.analysis.selection import CandidateSelection, discover_diagram_candidates
from visiogen.analysis.semantic_pipeline import SemanticAnalysisWorkflow
from visiogen.analysis.semantics import AnalyzedDiagram, RawObservationBatch
from visiogen.config import Settings
from visiogen.documents.extractor import extract_document
from visiogen.documents.models import DocumentSnapshot
from visiogen.documents.safety import DEFAULT_SAFETY_LIMITS
from visiogen.providers.codex_cli import CodexStructuredCaller

_REPOSITORY = Path(__file__).resolve().parents[3]


def _version_output(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if output else f"exit-{result.returncode}"


def _runtime_provenance(settings: Settings) -> RuntimeProvenance:
    revision = None
    clean = None
    if (_REPOSITORY / ".git").exists():
        revision_value = _version_output(
            ["git", "-C", str(_REPOSITORY), "rev-parse", "HEAD"]
        )
        if revision_value != "unavailable" and not revision_value.startswith("exit-"):
            revision = revision_value
            try:
                status = subprocess.run(
                    ["git", "-C", str(_REPOSITORY), "status", "--porcelain"],
                    text=True,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                clean = status.returncode == 0 and not status.stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                clean = None
    tools = {
        "python": platform.python_version(),
        "codex": _version_output([settings.codex_command, "--version"]),
    }
    for name in ("pdfinfo", "pdftotext", "pdftoppm"):
        executable = shutil.which(name)
        tools[name] = _version_output([executable, "-v"]) if executable else "unavailable"
    return RuntimeProvenance(
        source_revision=revision,
        source_worktree_clean=clean,
        tools=tools,
    )


class _SnapshotCandidateClassifier:
    def __init__(
        self,
        settings: Settings,
        snapshot: DocumentSnapshot,
        snapshot_dir: Path,
    ) -> None:
        self._settings = settings
        self._snapshot = snapshot
        self._snapshot_dir = snapshot_dir
        self.last_trace: CandidateClassificationTrace | None = None

    def classify(self, candidates: tuple[DiagramCandidate, ...]):
        assets = {item.id: item for item in self._snapshot.visual_assets}
        images = {
            candidate.id: self._snapshot_dir / assets[candidate.primary_asset_id].artifact_path
            for candidate in candidates
        }
        classifier = StructuredCandidateClassifier(
            CodexStructuredCaller(self._settings, VisualCandidateBatch),
            images,
            classifier_identity=f"codex-cli:{self._settings.codex_model}",
        )
        decisions = classifier.classify(candidates)
        self.last_trace = classifier.last_trace
        return decisions


class CodexDiscoveryStage:
    """Bind deterministic enumeration to one strict Codex visual classifier call."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.last_trace: CandidateClassificationTrace | None = None

    def __call__(
        self,
        snapshot: DocumentSnapshot,
        snapshot_dir: Path,
        options: AnalysisPipelineOptions,
    ) -> CandidateDiscovery:
        classifier = _SnapshotCandidateClassifier(
            self._settings,
            snapshot,
            snapshot_dir,
        )
        limits = replace(
            DEFAULT_SAFETY_LIMITS,
            max_diagram_candidates=options.max_diagrams,
        )
        discovery = discover_diagram_candidates(
            snapshot,
            snapshot_dir=snapshot_dir,
            classifier=classifier,
            selection=CandidateSelection(
                page_number=options.page_number,
                candidate_id=options.candidate_id,
            ),
            limits=limits,
        )
        self.last_trace = classifier.last_trace
        return discovery


def build_codex_analysis_pipeline(settings: Settings) -> DocumentAnalysisPipeline:
    """Construct production A1–A7 stages using the configured Codex vision model."""

    if settings.provider != "codex":
        raise ValueError("The production document-analysis pipeline currently requires Codex")
    discovery = CodexDiscoveryStage(settings)
    semantic = SemanticAnalysisWorkflow(
        StructuredObservationWorkflow(CodexStructuredCaller(settings, RawObservationBatch)),
        StructuredReconstructionWorkflow(CodexStructuredCaller(settings, AnalyzedDiagram)),
    )
    claims = StructuredClaimExtractionWorkflow(
        CodexStructuredCaller(settings, DocumentClaimBatch)
    )
    adjudicator = StructuredAdjudicationWorkflow(
        CodexStructuredCaller(settings, AdjudicationDecision)
    )
    return DocumentAnalysisPipeline(
        extract=extract_document,
        discover=discovery,
        prepare=prepare_diagram_candidates,
        semantic=semantic,
        claims=claims,
        adjudicator=adjudicator,
        provenance=lambda: _runtime_provenance(settings),
        provider="codex-cli",
        model=settings.codex_model,
        application_version="0.1.0",
        schema_models=(
            VisualCandidateBatch,
            RawObservationBatch,
            AnalyzedDiagram,
            DocumentClaimBatch,
            AdjudicationDecision,
        ),
    )
