"""Document-to-diagram analysis workstream.

This namespace owns diagram discovery, visual reconstruction, textual
description, claim extraction, and consistency analysis. It must not depend on
the text-to-VSDX renderer or generation pipeline.
"""

from visiogen.analysis.models import CandidateDiscovery, CandidatePreparation
from visiogen.analysis.preparation import prepare_diagram_candidates
from visiogen.analysis.selection import CandidateSelection, discover_diagram_candidates

__all__ = [
    "CandidateDiscovery",
    "CandidatePreparation",
    "CandidateSelection",
    "discover_diagram_candidates",
    "prepare_diagram_candidates",
]
