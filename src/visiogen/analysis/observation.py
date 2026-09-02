"""Overview-plus-tiles visual observation with one bounded structural repair."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import ValidationError

from visiogen.analysis.models import (
    AnalysisModel,
    PreparedCandidate,
    PreparedDerivative,
)
from visiogen.analysis.prompts import (
    build_observation_prompt,
    build_observation_repair_prompt,
)
from visiogen.analysis.semantics import RawObservationBatch, ValidatedObservationSet
from visiogen.analysis.validation import (
    AnalysisValidationError,
    normalize_duplicate_observation_ids,
    validate_observations,
)
from visiogen.providers.base import (
    ImageStructuredCall,
    ProviderResponse,
    ProviderTimeoutError,
)


class ObservationWorkflowError(ValueError):
    """Observation remained invalid within the configured attempt budget."""

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


class AnalysisCallTrace(AnalysisModel):
    """Exact prompt/response metadata for one A3 model call."""

    system_prompt: str
    user_prompt: str
    transport_prompt: str | None = None
    raw_response: str
    elapsed_ms: float
    image_sha256: dict[str, str]
    error_type: str | None = None
    error_message: str | None = None


class ObservationResult(AnalysisModel):
    """Validated observations and complete bounded-call provenance."""

    observations: ValidatedObservationSet
    attempts: int
    traces: list[AnalysisCallTrace]


def _model_derivatives(prepared: PreparedCandidate) -> list[PreparedDerivative]:
    overview = [item for item in prepared.derivatives if item.kind == "overview"]
    tiles = [item for item in prepared.derivatives if item.kind == "tile"]
    return overview + tiles


def _verified_images(
    prepared: PreparedCandidate,
    bundle_dir: Path,
) -> tuple[list[PreparedDerivative], list[Path], dict[str, str]]:
    if bundle_dir.is_symlink() or not bundle_dir.is_dir():
        raise ObservationWorkflowError("Candidate bundle must be a real directory")
    root = bundle_dir.resolve()
    derivatives = _model_derivatives(prepared)
    paths: list[Path] = []
    hashes: dict[str, str] = {}
    for derivative in derivatives:
        path = bundle_dir / derivative.artifact_path
        try:
            path.resolve().relative_to(root)
        except ValueError as error:
            raise ObservationWorkflowError("Candidate derivative escaped its bundle") from error
        if path.is_symlink() or not path.is_file():
            raise ObservationWorkflowError(f"Candidate derivative is missing: {derivative.id}")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if len(data) != derivative.byte_size or digest != derivative.sha256:
            raise ObservationWorkflowError(
                f"Candidate derivative no longer matches its manifest: {derivative.id}"
            )
        paths.append(path)
        hashes[derivative.id] = digest
    return derivatives, paths, hashes


def _inventory(candidate_id: str, derivatives: list[PreparedDerivative]) -> str:
    lines = [f"Candidate: {candidate_id}", "Images in attachment order:"]
    for index, item in enumerate(derivatives, start=1):
        lines.append(
            f"{index}. {item.id}; kind={item.kind}; pixels={item.width_px}x{item.height_px}; "
            f"source_region={item.source_region.model_dump_json()}"
        )
    return "\n".join(lines)


class StructuredObservationWorkflow:
    """Observe literal pixels and hard-validate them with at most one repair."""

    def __init__(self, call_model: ImageStructuredCall) -> None:
        self._call_model = call_model

    def observe(
        self,
        prepared: PreparedCandidate,
        bundle_dir: str | Path,
        *,
        max_attempts: int = 2,
    ) -> ObservationResult:
        if max_attempts not in {1, 2}:
            raise ValueError("Observation max_attempts must be one or two")
        derivatives, paths, image_hashes = _verified_images(prepared, Path(bundle_dir))
        system_prompt = build_observation_prompt()
        inventory = _inventory(prepared.candidate_id, derivatives)
        traces: list[AnalysisCallTrace] = []
        user_prompt = inventory
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
                    raise ObservationWorkflowError(
                        "Visual observation provider timed out within the configured attempt "
                        "budget",
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
                batch = RawObservationBatch.model_validate_json(response.content)
                batch = normalize_duplicate_observation_ids(batch)
                observations = validate_observations(batch, prepared)
                return ObservationResult(
                    observations=observations,
                    attempts=attempt,
                    traces=traces,
                )
            except (ValidationError, AnalysisValidationError) as error:
                if attempt == max_attempts:
                    raise ObservationWorkflowError(
                        "Visual observations are invalid within the configured attempt budget",
                        traces=traces,
                        validation_error=str(error),
                    ) from error
                user_prompt = build_observation_repair_prompt(
                    inventory,
                    response.content,
                    str(error),
                )
        raise AssertionError("Observation attempt loop did not return")
