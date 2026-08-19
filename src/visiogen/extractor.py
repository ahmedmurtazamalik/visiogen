"""Provider-neutral extraction boundary and geometry-free DTOs."""

from __future__ import annotations

from dataclasses import dataclass
import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from visiogen.models import (
    DiagramEdge,
    DiagramGraph,
    DiagramNode,
    DiagramType,
    DirectionType,
    LineStyle,
    NodeType,
    Orientation,
    RelationType,
)
from visiogen.normalization import GraphNormalizationError, normalize_extracted_graph
from visiogen.providers.base import (
    ExtractionValidationError,
    NoDiagramContentError,
    ProviderResponse,
    StructuredModelCall,
)


class ExtractionModel(BaseModel):
    """Base model that rejects provider fields outside the extraction schema."""

    model_config = ConfigDict(extra="forbid")


class ExtractedDiagramNode(ExtractionModel):
    """A semantic node DTO that deliberately has no geometry fields."""

    id: str
    type: NodeType
    label: str
    parent_id: str | None = None
    reference_number: str | None = None
    notes: str | None = None


class ExtractedDiagramEdge(ExtractionModel):
    """A semantic edge DTO whose ID may be assigned during normalization."""

    id: str | None = None
    source: str
    target: str
    relation: RelationType = "flow"
    direction: DirectionType = "forward"
    label: str | None = None
    style: LineStyle = "solid"


class ExtractedDiagramGraph(ExtractionModel):
    """Structured provider output before canonical normalization."""

    title: str
    diagram_type: DiagramType
    orientation: Orientation
    nodes: list[ExtractedDiagramNode] = Field(default_factory=list)
    edges: list[ExtractedDiagramEdge] = Field(default_factory=list)

    def to_diagram_graph(self) -> DiagramGraph:
        """Convert extraction DTOs to the canonical graph without adding semantics."""
        return DiagramGraph(
            title=self.title,
            diagram_type=self.diagram_type,
            orientation=self.orientation,
            nodes=[DiagramNode.model_validate(node.model_dump()) for node in self.nodes],
            edges=[DiagramEdge.model_validate(edge.model_dump()) for edge in self.edges],
        )


@dataclass(frozen=True, slots=True)
class ExtractionMetadata:
    """Safe model-call metadata that never stores prompts or credentials."""

    attempts: int
    request_ids: tuple[str, ...]
    elapsed_ms: float


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Canonical graph paired with safe extraction metadata."""

    graph: DiagramGraph
    metadata: ExtractionMetadata


def build_system_prompt() -> str:
    """Build the shared geometry-free structured extraction instruction."""

    schema = json.dumps(ExtractedDiagramGraph.model_json_schema(), sort_keys=True)
    return (
        "Extract only explicit or strongly implied diagram semantics as JSON. "
        "Never emit x, y, width, height, positions, or any layout geometry. "
        "Do not invent components, relationships, or reference numerals. "
        f"The response must satisfy this JSON Schema: {schema}"
    )


def build_repair_prompt(invalid_response: str, validation_error: str) -> str:
    """Request one schema-only correction without changing source semantics."""

    return (
        "Repair the following response so it satisfies the JSON schema. "
        "Return JSON only, preserve the source semantics, and add no geometry. "
        f"Validation error: {validation_error}\nInvalid response: {invalid_response}"
    )


class StructuredExtractionWorkflow:
    """Validate one model response through the canonical extraction boundary."""

    def __init__(self, call_model: StructuredModelCall) -> None:
        self._call_model = call_model

    def extract(self, text: str) -> DiagramGraph:
        return self.extract_with_metadata(text).graph

    @staticmethod
    def _validate(response: ProviderResponse) -> DiagramGraph:
        extracted = ExtractedDiagramGraph.model_validate_json(response.content)
        if not extracted.nodes:
            raise NoDiagramContentError("Provider output contains no diagram nodes")
        return normalize_extracted_graph(extracted.to_diagram_graph())

    def extract_with_metadata(self, text: str) -> ExtractionResult:
        if not text.strip():
            raise NoDiagramContentError("Input text is empty")
        system_prompt = build_system_prompt()
        first = self._call_model(system_prompt, text)
        responses = [first]
        try:
            graph = self._validate(first)
        except (ValidationError, GraphNormalizationError) as error:
            repaired = self._call_model(
                system_prompt,
                build_repair_prompt(first.content, str(error)),
            )
            responses.append(repaired)
            try:
                graph = self._validate(repaired)
            except (ValidationError, GraphNormalizationError) as repair_error:
                raise ExtractionValidationError(
                    "Provider output is invalid after one repair attempt"
                ) from repair_error

        return ExtractionResult(
            graph=graph,
            metadata=ExtractionMetadata(
                attempts=len(responses),
                request_ids=tuple(
                    response.request_id
                    for response in responses
                    if response.request_id is not None
                ),
                elapsed_ms=sum(response.elapsed_ms or 0.0 for response in responses),
            ),
        )
