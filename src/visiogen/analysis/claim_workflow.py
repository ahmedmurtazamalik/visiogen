"""Bounded structured A5 claim extraction from independently selected prose."""

from __future__ import annotations

from pydantic import Field, ValidationError

from visiogen.analysis.claim_prompts import build_claim_prompt, build_claim_repair_prompt
from visiogen.analysis.claim_validation import ClaimValidationError, validate_document_claims
from visiogen.analysis.claims import DocumentClaimBatch, TextSelection
from visiogen.analysis.models import AnalysisModel
from visiogen.providers.base import ProviderResponse, StructuredModelCall


class ClaimCallTrace(AnalysisModel):
    system_prompt: str
    user_prompt: str
    transport_prompt: str | None = None
    raw_response: str
    elapsed_ms: float = Field(ge=0)


class ClaimExtractionResult(AnalysisModel):
    claims: DocumentClaimBatch
    attempts: int = Field(ge=1, le=2)
    traces: list[ClaimCallTrace]


class ClaimExtractionWorkflowError(ValueError):
    pass


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
            response: ProviderResponse = self._call_model(system_prompt, user_prompt)
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
                batch = validate_document_claims(batch, selection)
                return ClaimExtractionResult(claims=batch, attempts=attempt, traces=traces)
            except (ValidationError, ClaimValidationError) as error:
                if attempt == 2:
                    raise ClaimExtractionWorkflowError(
                        f"Document claims are invalid after one repair attempt: {error}"
                    ) from error
                user_prompt = build_claim_repair_prompt(
                    selection_json,
                    response.content,
                    str(error),
                )
        raise AssertionError("Claim extraction attempt loop did not return")
