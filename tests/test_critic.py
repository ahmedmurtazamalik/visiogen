import json
from pathlib import Path

import pytest

from visiogen.critic import CritiqueError, StructuredVisualCritic, build_critique_prompt
from visiogen.design import DiagramDesign
from visiogen.providers.base import ProviderResponse


def design_data(processor_x: float = 6.0) -> dict:
    return {
        "graph": {
            "title": "Sensor system",
            "diagram_type": "system_block",
            "orientation": "left_to_right",
            "nodes": [
                {"id": "sensor", "type": "sensor", "label": "Sensor"},
                {"id": "processor", "type": "processor", "label": "Processor"},
            ],
            "edges": [
                {"id": "data", "source": "sensor", "target": "processor", "relation": "data", "direction": "forward", "style": "solid"}
            ],
        },
        "layout": {
            "composition": "balanced_hierarchy",
            "page_width": 8.0,
            "page_height": 5.0,
            "placements": [
                {"node_id": "sensor", "x": 2.0, "y": 2.5, "width": 1.5, "height": 1.0},
                {"node_id": "processor", "x": processor_x, "y": 2.5, "width": 1.8, "height": 1.0},
            ],
            "connector_hints": [{"edge_id": "data"}],
        },
        "rationale": "Direct flow.",
    }


class FakeImageCall:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = []

    def call_with_images(self, system_prompt, user_prompt, images):
        self.calls.append((system_prompt, user_prompt, images))
        return ProviderResponse(content=json.dumps(self.response), elapsed_ms=30.0)


def test_critique_prompt_requires_visible_evidence_and_one_revision() -> None:
    prompt = build_critique_prompt()

    assert "actual preview image" in prompt
    assert "connector crossings" in prompt
    assert "one" in prompt.lower()
    assert "structured" in prompt


def test_visual_critic_accepts_visible_drawing(tmp_path: Path) -> None:
    image = tmp_path / "preview.png"
    image.write_bytes(b"png")
    call = FakeImageCall(
        {
            "approved": True,
            "summary": "The composition is clear.",
            "issues": [],
            "revised_design": None,
        }
    )
    design = DiagramDesign.model_validate(design_data())

    result = StructuredVisualCritic(call).critique("Create a sensor system", design, image)

    assert result.critique.approved is True
    assert result.revised_design is None
    assert call.calls[0][2] == [image]
    assert "Create a sensor system" in call.calls[0][1]
    assert "Sensor system" in call.calls[0][1]


def test_visual_critic_returns_valid_complete_revised_design(tmp_path: Path) -> None:
    image = tmp_path / "preview.png"
    image.write_bytes(b"png")
    revised = design_data(processor_x=6.2)
    call = FakeImageCall(
        {
            "approved": False,
            "summary": "Increase the separation.",
            "issues": [
                {
                    "severity": "medium",
                    "category": "spacing",
                    "description": "The two shapes appear too close.",
                    "node_ids": ["sensor", "processor"],
                    "edge_ids": ["data"],
                }
            ],
            "revised_design": revised,
        }
    )

    result = StructuredVisualCritic(call).critique(
        "Create a sensor system",
        DiagramDesign.model_validate(design_data()),
        image,
    )

    assert result.critique.approved is False
    assert result.revised_design is not None
    assert result.revised_design.layout.placements[1].x == 6.2


def test_visual_critic_rejects_revision_without_complete_design(tmp_path: Path) -> None:
    image = tmp_path / "preview.png"
    image.write_bytes(b"png")
    call = FakeImageCall(
        {
            "approved": False,
            "summary": "Needs revision.",
            "issues": [],
            "revised_design": None,
        }
    )

    with pytest.raises(CritiqueError, match="revised_design"):
        StructuredVisualCritic(call).critique(
            "Create a sensor system",
            DiagramDesign.model_validate(design_data()),
            image,
        )
