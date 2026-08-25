"""Bounded A3 composition of observation and semantic reconstruction."""

from __future__ import annotations

from pathlib import Path

from visiogen.analysis.models import AnalysisModel, PreparedCandidate
from visiogen.analysis.observation import (
    ObservationResult,
    ObservationWorkflowError,
    StructuredObservationWorkflow,
)
from visiogen.analysis.reconstruction import (
    ReconstructionResult,
    ReconstructionWorkflowError,
    StructuredReconstructionWorkflow,
)
from visiogen.documents.safety import DEFAULT_SAFETY_LIMITS, DocumentSafetyLimits


class SemanticAnalysisResult(AnalysisModel):
    """Complete validated result for the two A3 model stages."""

    observation: ObservationResult
    reconstruction: ReconstructionResult
    total_model_calls: int


class SemanticAnalysisWorkflowError(RuntimeError):
    """A semantic stage failed while retaining every call made so far."""

    def __init__(
        self,
        stage: str,
        error: Exception,
        *,
        observation: ObservationResult | None = None,
    ) -> None:
        self.stage = stage
        self.original = error
        self.observation = observation
        prior = observation.traces if observation is not None else []
        self.traces = [*prior, *getattr(error, "traces", [])]
        self.validation_error = getattr(error, "validation_error", None)
        super().__init__(str(error))


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
        budget = self._limits.max_model_calls_per_candidate
        if budget < 2:
            raise RuntimeError("A3 workflow requires at least two model calls")
        try:
            observation = self._observation.observe(
                prepared,
                bundle_dir,
                max_attempts=min(2, budget - 1),
            )
        except ObservationWorkflowError as error:
            raise SemanticAnalysisWorkflowError("observation", error) from error
        remaining = budget - observation.attempts
        try:
            reconstruction = self._reconstruction.reconstruct(
                prepared,
                observation.observations,
                bundle_dir,
                max_attempts=min(2, remaining),
            )
        except ReconstructionWorkflowError as error:
            raise SemanticAnalysisWorkflowError(
                "reconstruction",
                error,
                observation=observation,
            ) from error
        total = observation.attempts + reconstruction.attempts
        if total > self._limits.max_model_calls_per_candidate:
            raise RuntimeError("A3 workflow exceeded the configured model-call budget")
        return SemanticAnalysisResult(
            observation=observation,
            reconstruction=reconstruction,
            total_model_calls=total,
        )
