"""Provider-neutral AI diagram-design workflow with one bounded repair."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from visiogen.design import DesignValidationError, DiagramDesign, validate_design
from visiogen.normalization import GraphNormalizationError
from visiogen.providers.base import ProviderResponse, StructuredModelCall


class DesignWorkflowError(ValueError):
    """Raised when a model cannot produce a valid hybrid diagram design."""


@dataclass(frozen=True, slots=True)
class DesignMetadata:
    """Safe aggregate metadata for the design and optional repair calls."""

    attempts: int
    request_ids: tuple[str, ...]
    elapsed_ms: float


@dataclass(frozen=True, slots=True)
class DesignResult:
    """Validated design plus the exact non-secret model responses for provenance."""

    design: DiagramDesign
    raw_responses: tuple[str, ...]
    user_prompts: tuple[str, ...]
    transport_prompts: tuple[str | None, ...]
    metadata: DesignMetadata


def build_design_prompt() -> str:
    """Build the shared hybrid semantic-and-visual design instruction."""

    schema = json.dumps(DiagramDesign.model_json_schema(), sort_keys=True)
    return (
        "Act as a diagram designer, not merely an entity extractor. Create a source-faithful "
        "semantic graph and a visually intentional one-page composition. Use your judgment for "
        "shape semantics, grouping, visual hierarchy, emphasis, balance, and connector flow. "
        "Provide complete center-based node coordinates and dimensions in page inches. Keep every "
        "rectangle inside the page, keep ordinary nodes from overlapping, and keep each child fully "
        "inside its container. Leave enough whitespace for labels, connectors, and reference "
        "callouts. Stochastic variation and alternative good compositions are welcome. Include only "
        "components and relationships supported by the source, but resolve genuine ambiguity using "
        "the most communicative interpretation. Avoid parallel connectors between the same two nodes "
        "when one relationship can communicate the meaning. When the same relation travels in both "
        "directions, prefer one bidirectional edge with a concise combined label such as Read / Write. "
        "IDs must be lowercase snake_case. Every placement "
        "must reference exactly one graph node. Connector hints must reference explicit edge IDs. "
        "Do not emit VSDX XML, Visio master IDs, ShapeSheet formulas, or implementation commands. "
        "Return JSON only. "
        f"The response must satisfy this JSON Schema: {schema}"
    )


def build_design_repair_prompt(
    source_text: str,
    invalid_response: str,
    validation_error: str,
) -> str:
    """Ask the same model to repair one rejected design using hard findings."""

    return (
        "Repair the previous diagram design using the hard validation findings below. Preserve the "
        "source meaning and the useful parts of the composition; change only what is needed to make "
        "the complete design valid. Return the entire schema-conforming design as JSON.\n\n"
        f"Original request:\n{source_text}\n\n"
        f"Hard validation findings:\n{validation_error}\n\n"
        f"Previous response:\n{invalid_response}"
    )


class StructuredDesignWorkflow:
    """Create and hard-validate an AI design with at most one repair call."""

    def __init__(self, call_model: StructuredModelCall) -> None:
        self._call_model = call_model

    @staticmethod
    def _validate(response: ProviderResponse) -> DiagramDesign:
        design = DiagramDesign.model_validate_json(response.content)
        return validate_design(design)

    def design(self, text: str) -> DesignResult:
        if not text.strip():
            raise DesignWorkflowError("Diagram request is empty")

        system_prompt = build_design_prompt()
        user_prompts = [text]
        first = self._call_model(system_prompt, text)
        responses = [first]
        try:
            design = self._validate(first)
        except (ValidationError, GraphNormalizationError, DesignValidationError) as error:
            repair_prompt = build_design_repair_prompt(text, first.content, str(error))
            user_prompts.append(repair_prompt)
            repaired = self._call_model(system_prompt, repair_prompt)
            responses.append(repaired)
            try:
                design = self._validate(repaired)
            except (ValidationError, GraphNormalizationError, DesignValidationError) as repair_error:
                raise DesignWorkflowError(
                    "AI design is invalid after one repair attempt"
                ) from repair_error

        return DesignResult(
            design=design,
            raw_responses=tuple(response.content for response in responses),
            user_prompts=tuple(user_prompts),
            transport_prompts=tuple(
                response.transport_prompt for response in responses
            ),
            metadata=DesignMetadata(
                attempts=len(responses),
                request_ids=tuple(
                    response.request_id
                    for response in responses
                    if response.request_id is not None
                ),
                elapsed_ms=sum(response.elapsed_ms or 0.0 for response in responses),
            ),
        )
