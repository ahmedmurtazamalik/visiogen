"""Document-to-diagram analysis workstream.

This namespace owns diagram discovery, visual reconstruction, textual
description, claim extraction, and consistency analysis. It must not depend on
the text-to-VSDX renderer or generation pipeline.
"""

from visiogen.analysis.description import (
    DiagramDescription,
    compose_diagram_description,
    render_description_markdown,
    write_description_bundle,
)
from visiogen.analysis.models import CandidateDiscovery, CandidatePreparation
from visiogen.analysis.observation import StructuredObservationWorkflow
from visiogen.analysis.preparation import prepare_diagram_candidates
from visiogen.analysis.reconstruction import StructuredReconstructionWorkflow
from visiogen.analysis.semantic_pipeline import SemanticAnalysisWorkflow
from visiogen.analysis.selection import CandidateSelection, discover_diagram_candidates

__all__ = [
    "CandidateDiscovery",
    "CandidatePreparation",
    "CandidateSelection",
    "DiagramDescription",
    "SemanticAnalysisWorkflow",
    "StructuredObservationWorkflow",
    "StructuredReconstructionWorkflow",
    "compose_diagram_description",
    "discover_diagram_candidates",
    "prepare_diagram_candidates",
    "render_description_markdown",
    "write_description_bundle",
]
