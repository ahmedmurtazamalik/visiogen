import json

import pytest

from visiogen.designer import (
    DesignWorkflowError,
    StructuredDesignWorkflow,
    build_design_prompt,
)
from visiogen.providers.base import ProviderResponse


def design_response(*, processor_x: float = 6.0) -> str:
    return json.dumps(
        {
            "graph": {
                "title": "Sensor system",
                "diagram_type": "system_block",
                "orientation": "left_to_right",
                "nodes": [
                    {"id": "sensor", "type": "sensor", "label": "Sensor", "parent_id": None, "reference_number": None, "notes": None},
                    {"id": "processor", "type": "processor", "label": "Processor", "parent_id": None, "reference_number": None, "notes": None},
                ],
                "edges": [
                    {
                        "id": "data_flow",
                        "source": "sensor",
                        "target": "processor",
                        "relation": "data",
                        "direction": "forward",
                        "label": None,
                        "style": "solid",
                    }
                ],
            },
            "layout": {
                "composition": "balanced_hierarchy",
                "page_width": 8.0,
                "page_height": 5.0,
                "placements": [
                    {"node_id": "sensor", "x": 2.0, "y": 2.5, "width": 1.5, "height": 1.0, "importance": "secondary"},
                    {"node_id": "processor", "x": processor_x, "y": 2.5, "width": 1.8, "height": 1.0, "importance": "primary"},
                ],
                "connector_hints": [
                    {"edge_id": "data_flow", "source_side": "right", "target_side": "left"}
                ],
            },
            "rationale": "Direct data flow with the processor emphasized.",
        }
    )


class FakeCall:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        self.calls.append((system_prompt, user_prompt))
        return ProviderResponse(content=next(self.responses), elapsed_ms=12.5)


def test_design_prompt_uses_ai_for_semantics_and_geometry() -> None:
    prompt = build_design_prompt()

    assert "visual hierarchy" in prompt
    assert "coordinates" in prompt
    assert "stochastic" in prompt
    assert "bidirectional" in prompt
    assert "VSDX XML" in prompt


def test_workflow_returns_real_response_and_validated_design() -> None:
    call = FakeCall([design_response()])

    result = StructuredDesignWorkflow(call).design("A sensor sends data to a processor")

    assert result.design.layout.placements[1].x == 6.0
    assert result.raw_responses == (design_response(),)
    assert result.metadata.attempts == 1
    assert result.metadata.elapsed_ms == 12.5
    assert len(call.calls) == 1
    assert "sensor sends data" in call.calls[0][1]


def test_workflow_returns_hard_validation_findings_for_one_repair() -> None:
    call = FakeCall([design_response(processor_x=2.2), design_response()])

    result = StructuredDesignWorkflow(call).design("A sensor system")

    assert result.metadata.attempts == 2
    assert "overlap" in call.calls[1][1]
    assert result.design.layout.placements[1].x == 6.0


def test_workflow_fails_after_invalid_repair() -> None:
    call = FakeCall(["not json", "still not json"])

    with pytest.raises(DesignWorkflowError, match="after one repair attempt"):
        StructuredDesignWorkflow(call).design("A sensor system")


def test_workflow_rejects_empty_input_before_model_call() -> None:
    call = FakeCall([design_response()])

    with pytest.raises(DesignWorkflowError, match="empty"):
        StructuredDesignWorkflow(call).design("  ")

    assert not call.calls
