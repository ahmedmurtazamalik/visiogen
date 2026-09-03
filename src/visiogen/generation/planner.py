"""AI construction planning with strict validation and one bounded repair."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from visiogen.generation.construction import (
    ConstructionPlanError,
    VisioConstructionPlan,
    validate_construction_plan,
)
from visiogen.generation.specification import DiagramSpecification
from visiogen.providers.base import ProviderResponse, StructuredModelCall

CONSTRUCTION_PROMPT_VERSION = 1
APPROVED_EXAMPLES_VERSION = 1

_APPROVED_EXAMPLES = """
Approved fixture patterns (use as drafting guidance, never as source facts):
- expert-flow.json: Start, Review, Finish share a horizontal guide; process and
  terminator masters; orthogonal end-arrow connectors; exact labels.
- expert-system.yaml: Sensor, Processor, Memory use sensor, controller, and database
  masters; reference numerals use one external reference callout each.
- expert-component.json: Housing uses the housing-container master with explicit
  header, padding, and member IDs; internal ports and external routes are explicit.
""".strip()


class ConstructionPlanningError(ValueError):
    """Raised when a plan remains invalid after one repair."""

    def __init__(
        self,
        message: str,
        *,
        responses: list[ProviderResponse],
        user_prompts: list[str],
    ) -> None:
        self.responses = tuple(responses)
        self.user_prompts = tuple(user_prompts)
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ConstructionPlanResult:
    plan: VisioConstructionPlan
    raw_responses: tuple[str, ...]
    user_prompts: tuple[str, ...]
    transport_prompts: tuple[str | None, ...]
    attempts: int
    request_ids: tuple[str, ...]
    elapsed_ms: float
    prompt_version: int = CONSTRUCTION_PROMPT_VERSION
    examples_version: int = APPROVED_EXAMPLES_VERSION


def build_construction_prompt() -> str:
    schema = json.dumps(VisioConstructionPlan.model_json_schema(), sort_keys=True)
    return (
        f"Create a complete professional VisioConstructionPlan from one validated "
        f"DiagramSpecification. Prompt version {CONSTRUCTION_PROMPT_VERSION}. The specification "
        "is authoritative: include every object and relationship exactly once, preserve labels, "
        "directions, containment, reference numerals, unknowns, hard constraints, and visual "
        "requirements. Choose exact known native template markers, page, regions, guides, shape "
        "and text rectangles, typography, fill and line styles, z-order, named ports, connector "
        "routes and bends, jumps, arrowheads, connector labels, container headers and padding, "
        "callout anchors and leaders, and traceability. Use top-left-origin page-inch coordinates. "
        "Do not emit VSDX XML, ShapeSheet formulas, package relationships, unsupported masters, "
        "or extra source facts. Return JSON only.\n\n"
        f"{_APPROVED_EXAMPLES}\n\n"
        f"The response must satisfy this JSON Schema: {schema}"
    )


def _input(specification: DiagramSpecification) -> str:
    return json.dumps(specification.model_dump(mode="json"), indent=2, sort_keys=True)


def _repair_prompt(specification: DiagramSpecification, response: str, error: str) -> str:
    return (
        "Repair the construction plan using only these deterministic findings. Preserve valid "
        "visual decisions and return the entire plan as JSON.\n\nSpecification:\n"
        f"{_input(specification)}\n\nFindings:\n{error}\n\nInvalid plan:\n{response}"
    )


class StructuredConstructionPlanner:
    """Plan and validate one construction, with at most one repair call."""

    def __init__(self, call_model: StructuredModelCall) -> None:
        self._call_model = call_model

    @staticmethod
    def _validate(
        specification: DiagramSpecification, response: ProviderResponse
    ) -> VisioConstructionPlan:
        plan = VisioConstructionPlan.model_validate_json(response.content)
        return validate_construction_plan(specification, plan)

    def plan(self, specification: DiagramSpecification) -> ConstructionPlanResult:
        system_prompt = build_construction_prompt()
        prompts = [_input(specification)]
        responses = [self._call_model(system_prompt, prompts[0])]
        try:
            plan = self._validate(specification, responses[0])
        except (ValidationError, ConstructionPlanError) as error:
            prompts.append(_repair_prompt(specification, responses[0].content, str(error)))
            responses.append(self._call_model(system_prompt, prompts[1]))
            try:
                plan = self._validate(specification, responses[1])
            except (ValidationError, ConstructionPlanError) as repair_error:
                raise ConstructionPlanningError(
                    "Construction plan is invalid after one repair attempt",
                    responses=responses,
                    user_prompts=prompts,
                ) from repair_error
        return ConstructionPlanResult(
            plan=plan,
            raw_responses=tuple(item.content for item in responses),
            user_prompts=tuple(prompts),
            transport_prompts=tuple(item.transport_prompt for item in responses),
            attempts=len(responses),
            request_ids=tuple(
                item.request_id for item in responses if item.request_id is not None
            ),
            elapsed_ms=sum(item.elapsed_ms or 0.0 for item in responses),
        )
