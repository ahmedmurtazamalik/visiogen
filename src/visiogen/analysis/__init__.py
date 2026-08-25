"""Document-to-diagram analysis workstream.

This namespace owns diagram discovery, visual reconstruction, textual
description, claim extraction, and consistency analysis. It must not depend on
the text-to-VSDX renderer or generation pipeline.
"""

from visiogen.analysis.alignment import align_claim_entities
from visiogen.analysis.adjudication import (
    AdjudicationRequest,
    StructuredAdjudicationWorkflow,
    apply_adjudication_decision,
    build_adjudication_request,
)
from visiogen.analysis.claim_workflow import StructuredClaimExtractionWorkflow
from visiogen.analysis.claims import (
    DocumentClaimBatch,
    EntityAlignmentSet,
    TextSelection,
)
from visiogen.analysis.comparison import (
    ConsistencyAnalysis,
    ConsistencyFinding,
    compare_diagram_and_claims,
    render_findings_markdown,
)
from visiogen.analysis.description import (
    DiagramDescription,
    compose_diagram_description,
    render_description_markdown,
    write_description_bundle,
)
from visiogen.analysis.models import CandidateDiscovery, CandidatePreparation
from visiogen.analysis.observation import StructuredObservationWorkflow
from visiogen.analysis.preparation import prepare_diagram_candidates
from visiogen.analysis.production import build_codex_analysis_pipeline
from visiogen.analysis.pipeline import (
    AnalysisPipelineOptions,
    DocumentAnalysis,
    DocumentAnalysisPipeline,
    DocumentAnalysisResult,
)
from visiogen.analysis.reconstruction import StructuredReconstructionWorkflow
from visiogen.analysis.semantic_pipeline import SemanticAnalysisWorkflow
from visiogen.analysis.selection import CandidateSelection, discover_diagram_candidates
from visiogen.analysis.text_selection import select_relevant_text

__all__ = [
    "CandidateDiscovery",
    "CandidatePreparation",
    "CandidateSelection",
    "AdjudicationRequest",
    "DocumentClaimBatch",
    "DiagramDescription",
    "EntityAlignmentSet",
    "ConsistencyAnalysis",
    "ConsistencyFinding",
    "AnalysisPipelineOptions",
    "DocumentAnalysis",
    "DocumentAnalysisPipeline",
    "DocumentAnalysisResult",
    "SemanticAnalysisWorkflow",
    "StructuredClaimExtractionWorkflow",
    "StructuredAdjudicationWorkflow",
    "StructuredObservationWorkflow",
    "StructuredReconstructionWorkflow",
    "align_claim_entities",
    "apply_adjudication_decision",
    "build_adjudication_request",
    "build_codex_analysis_pipeline",
    "compare_diagram_and_claims",
    "compose_diagram_description",
    "discover_diagram_candidates",
    "prepare_diagram_candidates",
    "render_description_markdown",
    "render_findings_markdown",
    "TextSelection",
    "select_relevant_text",
    "write_description_bundle",
]
