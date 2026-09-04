"""G8 vertical Generation v2 pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

from visiogen.generation.construction import VisioConstructionPlan
from visiogen.generation.pipeline import GenerationV2Pipeline
from visiogen.generation.planner import ConstructionPlanResult
from visiogen.generation.specification import load_specification
from visiogen.generation.specification_workflow import SpecificationResult
from visiogen.validation import validate_vsdx_package


SPECIFICATION = Path("tests/fixtures/generation_v2/specifications/expert-flow.json")
TEMPLATE = Path("templates/template.vsdx")


def _plan() -> VisioConstructionPlan:
    typography = {
        "family": "Arial",
        "size_pt": 11,
        "bold": False,
        "italic": False,
        "color": "#172033",
        "horizontal_align": "center",
        "vertical_align": "middle",
    }
    style = {
        "fill_color": "#EAF2FF",
        "line_color": "#274060",
        "line_weight_pt": 1.25,
        "line_pattern": "solid",
    }

    def shape(identifier: str, object_id: str, master: str, x: float) -> dict:
        rect = {"x": x, "y": 2.0, "width": 1.5, "height": 0.8}
        return {
            "id": identifier,
            "object_id": object_id,
            "master": master,
            "rect": rect,
            "text_box": rect,
            "typography": typography,
            "style": style,
            "z_order": 2,
            "ports": [
                {"name": "left", "side": "left", "offset": 0.5},
                {"name": "right", "side": "right", "offset": 0.5},
            ],
            "container": None,
        }

    def connector(
        identifier: str, relationship_id: str, source: str, target: str
    ) -> dict:
        return {
            "id": identifier,
            "relationship_id": relationship_id,
            "master": "__template_connector__",
            "connector_type": "straight",
            "source_shape_id": source,
            "source_port": "right",
            "target_shape_id": target,
            "target_port": "left",
            "waypoints": [],
            "bends": [],
            "jumps": False,
            "arrowheads": "end",
            "line_color": "#274060",
            "line_weight_pt": 1.25,
            "line_pattern": "solid",
            "label": None,
        }

    return VisioConstructionPlan.model_validate(
        {
            "version": 1,
            "specification_version": 1,
            "page": {
                "width": 10,
                "height": 5,
                "orientation": "landscape",
                "margin": 0.5,
                "grid": 0.25,
            },
            "regions": [],
            "guides": [
                {"id": "primary_axis", "axis": "horizontal", "position": 2.4}
            ],
            "shapes": [
                shape("shape_start", "start", "__template_terminator__", 0.8),
                shape("shape_review", "review", "__template_process__", 4.0),
                shape("shape_finish", "finish", "__template_terminator__", 7.2),
            ],
            "connectors": [
                connector(
                    "connector_start_review",
                    "start_review",
                    "shape_start",
                    "shape_review",
                ),
                connector(
                    "connector_review_finish",
                    "review_finish",
                    "shape_review",
                    "shape_finish",
                ),
            ],
            "callouts": [],
            "traceability": [
                {
                    "requirement_id": "primary_order",
                    "plan_element_ids": [
                        "shape_start",
                        "shape_review",
                        "shape_finish",
                        "primary_axis",
                    ],
                    "rationale": "The sequence is arranged from left to right.",
                },
                {
                    "requirement_id": "clear_labels",
                    "plan_element_ids": [
                        "shape_start",
                        "shape_review",
                        "shape_finish",
                    ],
                    "rationale": "Each label has a dedicated shape text box.",
                },
            ],
            "visual_rationale": "A restrained left-to-right review flow.",
        }
    )


class FakeSpecifier:
    def specify(self, text: str) -> SpecificationResult:
        specification = load_specification(SPECIFICATION)
        return SpecificationResult(
            specification=specification,
            raw_responses=(specification.model_dump_json(),),
            user_prompts=(text,),
            transport_prompts=("exact specification transport",),
            attempts=1,
            request_ids=("spec-1",),
            elapsed_ms=5,
        )


class FakePlanner:
    def plan(self, specification) -> ConstructionPlanResult:
        plan = _plan()
        return ConstructionPlanResult(
            plan=plan,
            raw_responses=(plan.model_dump_json(),),
            user_prompts=(specification.model_dump_json(),),
            transport_prompts=("exact construction transport",),
            attempts=1,
            request_ids=("plan-1",),
            elapsed_ms=7,
        )


def test_text_to_native_vsdx_vertical_pipeline_preserves_evidence(tmp_path: Path) -> None:
    output = tmp_path / "review-flow.vsdx"
    evidence = tmp_path / "evidence"
    pipeline = GenerationV2Pipeline(
        specifier=FakeSpecifier(),
        planner=FakePlanner(),
        template_path=TEMPLATE,
        provider="fake",
        model="fixture-v1",
    )

    progress = []
    result = pipeline.generate(
        "Create a start, review, and finish flow.",
        output,
        artifact_dir=evidence,
        progress=progress.append,
    )

    assert result.output_path == output
    validate_vsdx_package(output)
    assert (evidence / "04-validated-specification.json").is_file()
    assert (evidence / "07-validated-construction-plan.json").is_file()
    assert (evidence / "08-renderer-ir.json").is_file()
    assert (evidence / "09-final.vsdx").read_bytes() == output.read_bytes()
    manifest = json.loads((evidence / "manifest.json").read_text())
    assert manifest["architecture"] == "ai-directed-native-visio-v2"
    assert manifest["specification_request_ids"] == ["spec-1"]
    assert manifest["construction_request_ids"] == ["plan-1"]
    assert manifest["output_sha256"]
    assert manifest["renderer_ir_sha256"]
    assert manifest["windows_visio_acceptance"] == "pending"
    assert [event.stage for event in progress] == [
        "prepare",
        "specification",
        "specification_complete",
        "construction",
        "construction_complete",
        "compile",
        "render",
        "validate",
        "publish",
        "complete",
    ]
