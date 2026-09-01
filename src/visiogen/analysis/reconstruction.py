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
from visiogen.analysis.validation import (
    AnalysisValidationError,
    discard_unsupported_annotations,
    discard_unsupported_legends,
    downgrade_degraded_visible_labels,
    downgrade_unsupported_relationship_claims,
    downgrade_unsupported_relationship_endpoints,
    normalize_duplicate_relationship_ids,
    reground_visible_text_geometry,
    sanitize_object_grounding,
    validate_analyzed_diagram,
)
from visiogen.providers.base import (
    ImageStructuredCall,
    ProviderResponse,
    ProviderTimeoutError,
)


class ReconstructionWorkflowError(ValueError):
    """Semantic reconstruction remained invalid after one permitted repair."""

    def __init__(
        self,
        message: str,
        *,
        traces: list[AnalysisCallTrace] | None = None,
        validation_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.traces = traces or []
        self.validation_error = validation_error


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
        *,
        max_attempts: int = 2,
    ) -> ReconstructionResult:
        if max_attempts not in {1, 2}:
            raise ValueError("Reconstruction max_attempts must be one or two")
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
        for attempt in range(1, max_attempts + 1):
            try:
                response: ProviderResponse = self._call_model.call_with_images(
                    system_prompt,
                    user_prompt,
                    paths,
                )
            except ProviderTimeoutError as error:
                traces.append(
                    AnalysisCallTrace(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        transport_prompt=error.transport_prompt,
                        raw_response="",
                        elapsed_ms=error.elapsed_ms,
                        image_sha256=image_hashes,
                        error_type=type(error).__name__,
                        error_message=str(error),
                    )
                )
                if attempt == max_attempts:
                    raise ReconstructionWorkflowError(
                        "Semantic reconstruction provider timed out within the configured "
                        "attempt budget",
                        traces=traces,
                    ) from error
                continue
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
                diagram = normalize_duplicate_relationship_ids(diagram)
                diagram = sanitize_object_grounding(
                    diagram,
                    observations,
                    omit_unsupported=attempt == max_attempts,
                )
                diagram = discard_unsupported_legends(diagram, observations)
                diagram = discard_unsupported_annotations(diagram, observations)
                diagram = reground_visible_text_geometry(diagram, observations)
                diagram = downgrade_degraded_visible_labels(diagram, observations)
                diagram = downgrade_unsupported_relationship_claims(diagram, observations)
                diagram = downgrade_unsupported_relationship_endpoints(diagram)
                diagram = validate_analyzed_diagram(diagram, observations)
                return ReconstructionResult(
                    diagram=diagram,
                    attempts=attempt,
                    traces=traces,
                )
            except (ValidationError, AnalysisValidationError) as error:
                if attempt == max_attempts:
                    raise ReconstructionWorkflowError(
                        "Semantic reconstruction is invalid within the configured attempt budget: "
                        f"{error}",
                        traces=traces,
                        validation_error=str(error),
                    ) from error
                user_prompt = build_reconstruction_repair_prompt(
                    prepared.candidate_id,
                    observations_json,
                    response.content,
                    str(error),
                )
        raise AssertionError("Reconstruction attempt loop did not return")
