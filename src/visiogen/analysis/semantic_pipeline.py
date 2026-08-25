"""Bounded A3 composition of observation and semantic reconstruction."""

from __future__ import annotations

from pathlib import Path

from visiogen.analysis.models import AnalysisModel, PreparedCandidate
from visiogen.analysis.observation import ObservationResult, StructuredObservationWorkflow
from visiogen.analysis.reconstruction import (
    ReconstructionResult,
    StructuredReconstructionWorkflow,
)
from visiogen.documents.safety import DEFAULT_SAFETY_LIMITS, DocumentSafetyLimits


class SemanticAnalysisResult(AnalysisModel):
    """Complete validated result for the two A3 model stages."""

    observation: ObservationResult
    reconstruction: ReconstructionResult
    total_model_calls: int


class SemanticAnalysisWorkflow:
    """Run both A3 stages and enforce the configured total call budget."""

    def __init__(
        self,
        observation: StructuredObservationWorkflow,
        reconstruction: StructuredReconstructionWorkflow,
        *,
        limits: DocumentSafetyLimits = DEFAULT_SAFETY_LIMITS,
    ) -> None:
        self._observation = observation
        self._reconstruction = reconstruction
        self._limits = limits

    def analyze(
        self,
        prepared: PreparedCandidate,
        bundle_dir: str | Path,
    ) -> SemanticAnalysisResult:
        observation = self._observation.observe(prepared, bundle_dir)
        reconstruction = self._reconstruction.reconstruct(
            prepared,
            observation.observations,
            bundle_dir,
        )
        total = observation.attempts + reconstruction.attempts
        if total > self._limits.max_model_calls_per_candidate:
            raise RuntimeError("A3 workflow exceeded the configured model-call budget")
        return SemanticAnalysisResult(
            observation=observation,
            reconstruction=reconstruction,
            total_model_calls=total,
        )
