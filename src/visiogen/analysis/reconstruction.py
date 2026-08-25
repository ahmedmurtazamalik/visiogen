"""Evidence-grounded semantic reconstruction with one bounded repair."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from visiogen.analysis.models import AnalysisModel, PreparedCandidate
from visiogen.analysis.observation import AnalysisCallTrace, _verified_images
from visiogen.analysis.prompts import (
    build_reconstruction_prompt,
    build_reconstruction_repair_prompt,
)
from visiogen.analysis.semantics import AnalyzedDiagram, ValidatedObservationSet
from visiogen.analysis.validation import AnalysisValidationError, validate_analyzed_diagram
from visiogen.providers.base import ImageStructuredCall, ProviderResponse


class ReconstructionWorkflowError(ValueError):
    """Semantic reconstruction remained invalid after one permitted repair."""


class ReconstructionResult(AnalysisModel):
    """Validated semantic model and complete bounded-call provenance."""

    diagram: AnalyzedDiagram
    attempts: int
    traces: list[AnalysisCallTrace]


class StructuredReconstructionWorkflow:
    """Interpret validated observations without permitting unsupported labels."""

    def __init__(self, call_model: ImageStructuredCall) -> None:
        self._call_model = call_model

    def reconstruct(
        self,
        prepared: PreparedCandidate,
        observations: ValidatedObservationSet,
        bundle_dir: str | Path,
    ) -> ReconstructionResult:
        if prepared.candidate_id != observations.candidate_id:
            raise ReconstructionWorkflowError(
                "Prepared candidate and observations have different IDs"
            )
        _, paths, image_hashes = _verified_images(prepared, Path(bundle_dir))
        system_prompt = build_reconstruction_prompt()
        observations_json = observations.model_dump_json(indent=2)
        user_prompt = (
            f"Candidate: {prepared.candidate_id}\n\n"
            f"Validated observations in source-image coordinates:\n{observations_json}"
        )
        traces: list[AnalysisCallTrace] = []
        for attempt in (1, 2):
            response: ProviderResponse = self._call_model.call_with_images(
                system_prompt,
                user_prompt,
                paths,
            )
            traces.append(
                AnalysisCallTrace(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    transport_prompt=response.transport_prompt,
                    raw_response=response.content,
                    elapsed_ms=response.elapsed_ms or 0,
                    image_sha256=image_hashes,
                )
            )
            try:
                diagram = AnalyzedDiagram.model_validate_json(response.content)
                diagram = validate_analyzed_diagram(diagram, observations)
                return ReconstructionResult(
                    diagram=diagram,
                    attempts=attempt,
                    traces=traces,
                )
            except (ValidationError, AnalysisValidationError) as error:
                if attempt == 2:
                    raise ReconstructionWorkflowError(
                        "Semantic reconstruction is invalid after one repair attempt"
                    ) from error
                user_prompt = build_reconstruction_repair_prompt(
                    prepared.candidate_id,
                    observations_json,
                    response.content,
                    str(error),
                )
        raise AssertionError("Reconstruction attempt loop did not return")
