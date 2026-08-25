"""Bounded fake-runner contracts for A3 observation and reconstruction."""

import hashlib
import json
from pathlib import Path

from PIL import Image

from visiogen.analysis.models import PreparedCandidate, PreparedDerivative
from visiogen.analysis.observation import StructuredObservationWorkflow
from visiogen.analysis.reconstruction import StructuredReconstructionWorkflow
from visiogen.analysis.semantic_pipeline import SemanticAnalysisWorkflow
from visiogen.documents.models import NormalizedBox
from visiogen.providers.base import ProviderResponse


class FakeImageCall:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = []

    def call_with_images(self, system_prompt, user_prompt, images):
        self.calls.append((system_prompt, user_prompt, list(images)))
        return ProviderResponse(
            content=next(self.responses),
            elapsed_ms=10,
            transport_prompt="transport",
        )


def _prepared_bundle(tmp_path: Path) -> tuple[PreparedCandidate, Path]:
    bundle = tmp_path / "prepared"
    assets = bundle / "assets"
    assets.mkdir(parents=True)
    paths = []
    for name in ("crop", "overview", "tile"):
        path = assets / f"{name}.png"
        Image.new("RGB", (100, 100), "white").save(path)
        paths.append(path)
    full = NormalizedBox(left=0, top=0, right=1, bottom=1)
    derivatives = []
    for kind, path in zip(("crop", "overview", "tile"), paths, strict=True):
        data = path.read_bytes()
        derivatives.append(
            PreparedDerivative(
                id=f"candidate-0001-{kind}",
                kind=kind,
                artifact_path=f"assets/{path.name}",
                sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data),
                width_px=100,
                height_px=100,
                source_region=full,
            )
        )
    return PreparedCandidate(candidate_id="candidate-0001", derivatives=derivatives), bundle


def _observation_response(*, evidence_id: str = "evidence-0001") -> str:
    return json.dumps(
        {
            "candidate_id": "candidate-0001",
            "evidence": [
                {
                    "id": "evidence-0001",
                    "derivative_id": "candidate-0001-overview",
                    "local_bbox": {"left": 0.1, "top": 0.1, "right": 0.4, "bottom": 0.3},
                }
            ],
            "observations": [
                {
                    "id": "observation-0001",
                    "kind": "visible_text",
                    "geometry_derivative_id": "candidate-0001-overview",
                    "local_bbox": {"left": 0.1, "top": 0.1, "right": 0.4, "bottom": 0.3},
                    "local_path": [],
                    "visible_text": "Sensor",
                    "properties": [],
                    "evidence_ids": [evidence_id],
                    "confidence": "high",
                    "alternatives": [],
                }
            ],
            "warnings": [],
        }
    )


def _diagram_response(*, label: str = "Sensor") -> str:
    return json.dumps(
        {
            "candidate_id": "candidate-0001",
            "title": None,
            "family": "system_block",
            "orientation": "left_to_right",
            "objects": [
                {
                    "id": "object-0001",
                    "visible_label": label,
                    "normalized_label": label.casefold(),
                    "semantic_type": "sensor",
                    "visual_shape": "rectangle",
                    "reference_numbers": [],
                    "parent_id": None,
                    "bbox": {"left": 0.1, "top": 0.1, "right": 0.4, "bottom": 0.3},
                    "evidence_ids": ["evidence-0001"],
                    "confidence": "high",
                    "alternatives": [],
                }
            ],
            "relationships": [],
            "groups": [],
            "legends": [],
            "limitations": [],
            "confidence": "high",
        }
    )


def test_observation_workflow_uses_overview_tiles_and_one_repair(tmp_path: Path) -> None:
    prepared, bundle = _prepared_bundle(tmp_path)
    caller = FakeImageCall(
        [_observation_response(evidence_id="missing"), _observation_response()]
    )

    result = StructuredObservationWorkflow(caller).observe(prepared, bundle)

    assert result.attempts == 2
    assert len(result.traces) == 2
    assert [path.name for path in caller.calls[0][2]] == ["overview.png", "tile.png"]
    assert "Hard validation findings" in caller.calls[1][1]
    assert result.observations.observations[0].visible_text == "Sensor"


def test_reconstruction_workflow_rejects_invention_then_repairs(tmp_path: Path) -> None:
    prepared, bundle = _prepared_bundle(tmp_path)
    observation_call = FakeImageCall([_observation_response()])
    observations = StructuredObservationWorkflow(observation_call).observe(
        prepared,
        bundle,
    ).observations
    reconstruction_call = FakeImageCall(
        [_diagram_response(label="Invented"), _diagram_response()]
    )

    result = StructuredReconstructionWorkflow(reconstruction_call).reconstruct(
        prepared,
        observations,
        bundle,
    )

    assert result.attempts == 2
    assert result.diagram.objects[0].visible_label == "Sensor"
    assert "Do not invent" in reconstruction_call.calls[1][1]


def test_semantic_pipeline_composes_both_stages_with_bounded_calls(tmp_path: Path) -> None:
    prepared, bundle = _prepared_bundle(tmp_path)
    observation = StructuredObservationWorkflow(FakeImageCall([_observation_response()]))
    reconstruction = StructuredReconstructionWorkflow(FakeImageCall([_diagram_response()]))

    result = SemanticAnalysisWorkflow(observation, reconstruction).analyze(
        prepared,
        bundle,
    )

    assert result.total_model_calls == 2
    assert result.observation.observations.candidate_id == "candidate-0001"
    assert result.reconstruction.diagram.objects[0].visible_label == "Sensor"
