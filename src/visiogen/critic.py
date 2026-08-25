"""Structured multimodal critique of actual generated diagram previews."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from visiogen.design import DesignValidationError, DiagramDesign, validate_design
from visiogen.normalization import GraphNormalizationError
from visiogen.providers.base import ImageStructuredCall

IssueSeverity = Literal["low", "medium", "high"]
IssueCategory = Literal[
    "source_fidelity",
    "hierarchy",
    "spacing",
    "overlap",
    "connector_crossing",
    "connector_clarity",
    "obstruction",
    "label_readability",
    "balance",
    "containment",
    "other",
]


class CritiqueModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisualIssue(CritiqueModel):
    """One issue grounded in the actual rendered preview."""

    severity: IssueSeverity
    category: IssueCategory
    description: str
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)


class VisualCritique(CritiqueModel):
    """Approval or one complete revised design from image review."""

    approved: bool
    summary: str
    issues: list[VisualIssue] = Field(default_factory=list)
    revised_design: DiagramDesign | None = None


class CritiqueError(ValueError):
    """Raised when visual critique is absent, inconsistent, or invalid."""


@dataclass(frozen=True, slots=True)
class CritiqueResult:
    """Validated critique and exact raw response for provenance."""

    critique: VisualCritique
    revised_design: DiagramDesign | None
    raw_response: str
    user_prompt: str
    transport_prompt: str | None
    elapsed_ms: float


def build_critique_prompt() -> str:
    """Build the shared image-grounded visual-review instruction."""

    schema = json.dumps(VisualCritique.model_json_schema(), sort_keys=True)
    return (
        "Inspect the actual preview image of a generated editable diagram. Judge the visible result "
        "against the original request and structured design. Check source fidelity, visual hierarchy, "
        "balance, spacing, containment, label readability, connector crossings, connector clarity, "
        "arrows passing through unrelated shapes, and callout obstruction. Report only issues visible "
        "in the supplied image or directly contradicted by the supplied request/design. If the draft "
        "is already clear, approve it and set revised_design to null. Otherwise produce exactly one "
        "complete structured revised design, preserving good semantics while correcting the identified "
        "problems. The revision must contain complete valid geometry for every node and remain within "
        "one page. You may combine visually confusing reciprocal edges into one bidirectional edge when "
        "that preserves the source meaning. Do not propose VSDX XML or ShapeSheet edits. Return JSON only. "
        f"The response must satisfy this JSON Schema: {schema}"
    )


def build_critique_user_prompt(source_text: str, design: DiagramDesign) -> str:
    """Build the exact image-critique request retained in provenance."""

    return (
        f"Original request:\n{source_text}\n\n"
        "Structured design used for this preview:\n"
        f"{design.model_dump_json(indent=2)}"
    )


class StructuredVisualCritic:
    """Run one real image critique and validate any proposed complete revision."""

    def __init__(self, call_model: ImageStructuredCall) -> None:
        self._call_model = call_model

    def critique(
        self,
        source_text: str,
        design: DiagramDesign,
        preview_path: str | Path,
    ) -> CritiqueResult:
        image = Path(preview_path)
        if not image.is_file():
            raise CritiqueError(f"Preview image was not found: {image}")
        user_prompt = build_critique_user_prompt(source_text, design)
        response = self._call_model.call_with_images(
            build_critique_prompt(),
            user_prompt,
            [image],
        )
        try:
            critique = VisualCritique.model_validate_json(response.content)
        except ValidationError as error:
            raise CritiqueError("Visual critic returned invalid structured output") from error

        if critique.approved and critique.revised_design is not None:
            raise CritiqueError("Approved critique must set revised_design to null")
        if not critique.approved and critique.revised_design is None:
            raise CritiqueError("Rejected critique must include a complete revised_design")

        revised = critique.revised_design
        if revised is not None:
            try:
                revised = validate_design(revised)
            except (DesignValidationError, GraphNormalizationError) as error:
                raise CritiqueError("Visual critic returned an invalid revised_design") from error

        return CritiqueResult(
            critique=critique,
            revised_design=revised,
            raw_response=response.content,
            user_prompt=user_prompt,
            transport_prompt=response.transport_prompt,
            elapsed_ms=response.elapsed_ms or 0.0,
        )
