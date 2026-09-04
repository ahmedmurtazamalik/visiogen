"""Model-assisted natural-language to DiagramSpecification workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from visiogen.generation.specification import DiagramSpecification
from visiogen.providers.base import ProviderResponse, StructuredModelCall


_CONSTRAINT_FIELD_RULES = (
    "Constraint field rules: ordering and adjacency use axis=null and "
    "minimum_distance=null; alignment requires axis and uses "
    "minimum_distance=null; separation requires axis=null and a positive "
    "minimum_distance. Never invent a numeric separation distance: if the "
    "request does not supply one, omit that separation constraint and express "
    "the qualitative preference elsewhere."
)


class SpecificationWorkflowError(ValueError):
    """Raised when text cannot produce a valid specification after one repair."""

    def __init__(
        self,
        message: str,
        *,
        responses: list[ProviderResponse] | None = None,
        user_prompts: list[str] | None = None,
        validation_error: str | None = None,
    ) -> None:
        self.responses = tuple(responses or ())
        self.user_prompts = tuple(user_prompts or ())
        self.validation_error = validation_error
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SpecificationResult:
    specification: DiagramSpecification
    raw_responses: tuple[str, ...]
    user_prompts: tuple[str, ...]
    transport_prompts: tuple[str | None, ...]
    attempts: int
    request_ids: tuple[str, ...]
    elapsed_ms: float


def build_specification_prompt() -> str:
    schema = json.dumps(DiagramSpecification.model_json_schema(), sort_keys=True)
    return (
        "Convert the request into a source-faithful professional diagram specification. "
        "Record purpose, audience, notation, objects, relationships, labels, reference "
        "numerals, containment, importance, primary flow, drafting preferences, composition "
        "constraints, measurable visual requirements, forbidden conditions, and explicit "
        "ambiguities or unknowns. Use lowercase snake_case IDs. Do not invent facts or resolve "
        "uncertainty silently. Hard constraints must be internally consistent. Do not choose "
        "coordinates, routes, VSDX XML, Visio masters, or ShapeSheet formulas. Return JSON only. "
        f"{_CONSTRAINT_FIELD_RULES} "
        f"The response must satisfy this JSON Schema: {schema}"
    )


def _repair_prompt(text: str, response: str, error: str) -> str:
    return (
        "Repair the invalid DiagramSpecification using only the validation findings. Preserve "
        "the request semantics and return the complete JSON object. "
        f"{_CONSTRAINT_FIELD_RULES}\n\n"
        f"Original request:\n{text}\n\nValidation findings:\n{error}\n\n"
        f"Invalid response:\n{response}"
    )


class StructuredSpecificationWorkflow:
    """Create a strict specification with one bounded schema/constraint repair."""

    def __init__(self, call_model: StructuredModelCall) -> None:
        self._call_model = call_model

    def specify(self, text: str) -> SpecificationResult:
        if not text.strip():
            raise SpecificationWorkflowError("Diagram request is empty")
        system_prompt = build_specification_prompt()
        prompts = [text]
        responses = [self._call_model(system_prompt, text)]
        try:
            specification = DiagramSpecification.model_validate_json(responses[0].content)
        except ValidationError as error:
            prompts.append(_repair_prompt(text, responses[0].content, str(error)))
            responses.append(self._call_model(system_prompt, prompts[-1]))
            try:
                specification = DiagramSpecification.model_validate_json(responses[1].content)
            except ValidationError as repair_error:
                raise SpecificationWorkflowError(
                    "Specification is invalid after one repair attempt: "
                    f"{repair_error}",
                    responses=responses,
                    user_prompts=prompts,
                    validation_error=str(repair_error),
                ) from repair_error
        return SpecificationResult(
            specification=specification,
            raw_responses=tuple(item.content for item in responses),
            user_prompts=tuple(prompts),
            transport_prompts=tuple(item.transport_prompt for item in responses),
            attempts=len(responses),
            request_ids=tuple(
                item.request_id for item in responses if item.request_id is not None
            ),
            elapsed_ms=sum(item.elapsed_ms or 0.0 for item in responses),
        )
