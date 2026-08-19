import json

import pytest
from pydantic import ValidationError

from visiogen.extractor import (
    ExtractedDiagramGraph,
    StructuredExtractionWorkflow,
    build_system_prompt,
)
from visiogen.models import DiagramGraph
from visiogen.providers.base import (
    ExtractionValidationError,
    NoDiagramContentError,
    ProviderResponse,
)


def extracted_payload() -> dict:
    return {
        "title": "Sensor system",
        "diagram_type": "system_block",
        "orientation": "left_to_right",
        "nodes": [
            {"id": "sensor", "type": "sensor", "label": "Sensor"},
            {"id": "controller", "type": "controller", "label": "Controller"},
        ],
        "edges": [
            {
                "source": "sensor",
                "target": "controller",
                "relation": "data",
                "direction": "forward",
            }
        ],
    }


def test_extraction_dto_converts_semantics_to_canonical_graph():
    extracted = ExtractedDiagramGraph.model_validate(extracted_payload())

    graph = extracted.to_diagram_graph()

    assert isinstance(graph, DiagramGraph)
    assert graph.nodes[0].type == "sensor"
    assert graph.edges[0].relation == "data"
    assert graph.has_geometry is False


def test_extraction_dto_rejects_geometry_fields():
    payload = extracted_payload()
    payload["nodes"][0]["x"] = 1.0

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExtractedDiagramGraph.model_validate(payload)


def test_extraction_dto_allows_missing_edge_id_for_normalization():
    extracted = ExtractedDiagramGraph.model_validate(extracted_payload())

    assert extracted.to_diagram_graph().edges[0].id is None


def test_workflow_accepts_valid_first_response() -> None:
    calls: list[tuple[str, str]] = []

    def call_model(system_prompt: str, user_prompt: str) -> ProviderResponse:
        calls.append((system_prompt, user_prompt))
        return ProviderResponse(
            content=json.dumps(extracted_payload()),
            request_id="request-1",
            elapsed_ms=12.5,
        )

    result = StructuredExtractionWorkflow(call_model).extract_with_metadata(
        "A sensor sends data to a controller."
    )

    assert result.graph.nodes[0].type == "sensor"
    assert result.graph.has_geometry is False
    assert result.metadata.attempts == 1
    assert result.metadata.request_ids == ("request-1",)
    assert calls[0][1] == "A sensor sends data to a controller."


def test_workflow_repairs_one_invalid_response() -> None:
    responses = iter(
        [
            ProviderResponse("not JSON", request_id="bad", elapsed_ms=2.0),
            ProviderResponse(
                json.dumps(extracted_payload()),
                request_id="fixed",
                elapsed_ms=3.0,
            ),
        ]
    )
    calls: list[tuple[str, str]] = []

    def call_model(system_prompt: str, user_prompt: str) -> ProviderResponse:
        calls.append((system_prompt, user_prompt))
        return next(responses)

    result = StructuredExtractionWorkflow(call_model).extract_with_metadata(
        "A sensor sends data to a controller."
    )

    assert result.graph.nodes[1].type == "controller"
    assert result.metadata.attempts == 2
    assert result.metadata.request_ids == ("bad", "fixed")
    assert result.metadata.elapsed_ms == 5.0
    assert "not JSON" in calls[1][1]
    assert "validation" in calls[1][1].lower()


def test_workflow_fails_after_exactly_two_invalid_responses() -> None:
    attempts = 0

    def call_model(system_prompt: str, user_prompt: str) -> ProviderResponse:
        nonlocal attempts
        attempts += 1
        return ProviderResponse("still not JSON")

    with pytest.raises(
        ExtractionValidationError,
        match="invalid after one repair attempt",
    ):
        StructuredExtractionWorkflow(call_model).extract("A sensor system")

    assert attempts == 2


def test_empty_text_fails_before_provider_invocation() -> None:
    invoked = False

    def call_model(system_prompt: str, user_prompt: str) -> ProviderResponse:
        nonlocal invoked
        invoked = True
        raise AssertionError("provider must not be invoked")

    with pytest.raises(NoDiagramContentError, match="Input text is empty"):
        StructuredExtractionWorkflow(call_model).extract("  \n")

    assert invoked is False


def test_semantically_empty_provider_output_raises_no_diagram_content() -> None:
    payload = {
        "title": "No diagram",
        "diagram_type": "flowchart",
        "orientation": "top_to_bottom",
        "nodes": [],
        "edges": [],
    }

    def call_model(system_prompt: str, user_prompt: str) -> ProviderResponse:
        return ProviderResponse(json.dumps(payload))

    with pytest.raises(NoDiagramContentError, match="no diagram nodes"):
        StructuredExtractionWorkflow(call_model).extract("Nothing definite was described")


def test_system_prompt_requires_minimal_source_faithful_semantics() -> None:
    prompt = build_system_prompt().lower()

    assert "source wording" in prompt
    assert "snake_case" in prompt
    assert "do not add an edge label" in prompt
    assert "do not invent a decision node" in prompt
    assert "software service" in prompt
    assert "transducer" in prompt
    assert "audio driver" in prompt
    assert "energy-harvesting" in prompt
    assert "user input" in prompt
    assert "processor and memory" in prompt
    assert "relation word" in prompt
    assert "start terminator" in prompt
