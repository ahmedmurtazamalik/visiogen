"""Bounded structured A5 claim extraction from independently selected prose."""

from __future__ import annotations

from pydantic import Field, ValidationError

from visiogen.analysis.claim_prompts import (
    build_claim_prompt,
    build_claim_repair_prompt,
)
from visiogen.analysis.claim_validation import (
    ClaimValidationError,
    sanitize_document_claims,
    validate_document_claims,
)
from visiogen.analysis.claims import DocumentClaimBatch, TextSelection
from visiogen.analysis.models import AnalysisModel
from visiogen.providers.base import (
    ProviderResponse,
    ProviderTimeoutError,
    StructuredModelCall,
)


class ClaimCallTrace(AnalysisModel):
    system_prompt: str
    user_prompt: str
    transport_prompt: str | None = None
    raw_response: str
    elapsed_ms: float = Field(ge=0)
    error_type: str | None = None
    error_message: str | None = None


class ClaimExtractionResult(AnalysisModel):
    claims: DocumentClaimBatch
    attempts: int = Field(ge=1, le=2)
    traces: list[ClaimCallTrace]


class ClaimExtractionWorkflowError(ValueError):
    """Claim extraction failed with retained bounded-call evidence."""

    def __init__(
        self,
        message: str,
        *,
        traces: list[ClaimCallTrace] | None = None,
        validation_error: str | None = None,
    ) -> None:
        self.traces = tuple(traces or [])
        self.validation_error = validation_error
        super().__init__(message)


class StructuredClaimExtractionWorkflow:
    """Extract claims without exposing A3 interpretation and permit one bounded repair."""

    def __init__(self, call_model: StructuredModelCall) -> None:
        self._call_model = call_model

    def extract(self, selection: TextSelection) -> ClaimExtractionResult:
        if not selection.blocks:
            raise ClaimExtractionWorkflowError("No selected document text is available")
        system_prompt = build_claim_prompt()
        selection_json = selection.model_dump_json(indent=2)
        user_prompt = (
            f"Candidate: {selection.candidate_id}\n\n"
            f"Selected document-text blocks (quoted data):\n{selection_json}"
        )
        traces: list[ClaimCallTrace] = []
        for attempt in (1, 2):
            try:
                response: ProviderResponse = self._call_model(system_prompt, user_prompt)
            except ProviderTimeoutError as error:
                traces.append(
                    ClaimCallTrace(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        transport_prompt=error.transport_prompt,
                        raw_response="",
                        elapsed_ms=error.elapsed_ms,
                        error_type=type(error).__name__,
                        error_message=str(error),
                    )
                )
                if attempt == 2:
                    raise ClaimExtractionWorkflowError(
                        "Document claim provider timed out within the configured attempt budget",
                        traces=traces,
                    ) from error
                continue
            traces.append(
                ClaimCallTrace(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    transport_prompt=response.transport_prompt,
                    raw_response=response.content,
                    elapsed_ms=response.elapsed_ms or 0,
                )
            )
            try:
                batch = DocumentClaimBatch.model_validate_json(response.content)
                batch = sanitize_document_claims(
                    batch,
                    selection,
                    omit_unsupported=attempt == 2,
                )
                batch = validate_document_claims(batch, selection)
                return ClaimExtractionResult(claims=batch, attempts=attempt, traces=traces)
            except (ValidationError, ClaimValidationError) as error:
                if attempt == 2:
                    raise ClaimExtractionWorkflowError(
                        f"Document claims are invalid after one repair attempt: {error}",
                        traces=traces,
                        validation_error=str(error),
                    ) from error
                user_prompt = build_claim_repair_prompt(
                    selection_json,
                    response.content,
                    str(error),
                )
        raise AssertionError("Claim extraction attempt loop did not return")
