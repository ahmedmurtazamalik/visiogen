"""Bounded fake-runner contracts for A3 observation and reconstruction."""

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from visiogen.analysis.models import PreparedCandidate, PreparedDerivative
from visiogen.analysis.observation import (
    ObservationWorkflowError,
    StructuredObservationWorkflow,
)
from visiogen.analysis.prompts import (
    build_reconstruction_prompt,
    build_reconstruction_repair_prompt,
)
from visiogen.analysis.reconstruction import (
    ReconstructionWorkflowError,
    StructuredReconstructionWorkflow,
)
from visiogen.analysis.semantic_pipeline import (
    SemanticAnalysisWorkflow,
    SemanticAnalysisWorkflowError,
)
from visiogen.documents.models import NormalizedBox
from visiogen.documents.safety import DocumentSafetyLimits
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


def _diagram_response_with_unsupported_legend() -> str:
    payload = json.loads(_diagram_response())
    payload["legends"] = [
        {
            "symbol": "solid",
            "meaning": "Invented meaning",
            "evidence_ids": ["evidence-0001"],
            "confidence": "high",
        }
    ]
    return json.dumps(payload)


def _diagram_response_with_unsupported_annotation() -> str:
    payload = json.loads(_diagram_response())
    payload["annotations"] = [
        {
            "id": "annotation-0001",
            "kind": "callout",
            "visible_text": "Invented callout",
            "attached_object_ids": ["object-0001"],
            "bbox": {"left": 0.1, "top": 0.1, "right": 0.4, "bottom": 0.3},
            "evidence_ids": ["evidence-0001"],
            "confidence": "high",
            "alternatives": [],
        }
    ]
    return json.dumps(payload)


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


def test_reconstruction_failure_preserves_validation_evidence(tmp_path: Path) -> None:
    prepared, bundle = _prepared_bundle(tmp_path)
    observations = StructuredObservationWorkflow(
        FakeImageCall([_observation_response()])
    ).observe(prepared, bundle).observations

    with pytest.raises(ReconstructionWorkflowError) as caught:
        StructuredReconstructionWorkflow(
            FakeImageCall([_diagram_response(label="Invented")] * 2)
        ).reconstruct(prepared, observations, bundle)

    assert "not present in cited evidence" in str(caught.value)
    assert "not present in cited evidence" in (caught.value.validation_error or "")
    assert "Invented" in caught.value.traces[-1].raw_response
    assert len(caught.value.traces) == 2


def test_reconstruction_discards_unsupported_legend_without_repair_call(
    tmp_path: Path,
) -> None:
    prepared, bundle = _prepared_bundle(tmp_path)
    observations = StructuredObservationWorkflow(
        FakeImageCall([_observation_response()])
    ).observe(prepared, bundle).observations
    caller = FakeImageCall([_diagram_response_with_unsupported_legend()])

    result = StructuredReconstructionWorkflow(caller).reconstruct(
        prepared,
        observations,
        bundle,
    )

    assert result.attempts == 1
    assert result.diagram.legends == []
    assert result.diagram.limitations == [
        "Omitted 1 legend mapping whose meaning was not literally visible in cited evidence."
    ]
    assert len(caller.calls) == 1


def test_reconstruction_discards_unsupported_annotation_without_repair_call(
    tmp_path: Path,
) -> None:
    prepared, bundle = _prepared_bundle(tmp_path)
    observations = StructuredObservationWorkflow(
        FakeImageCall([_observation_response()])
    ).observe(prepared, bundle).observations
    caller = FakeImageCall([_diagram_response_with_unsupported_annotation()])

    result = StructuredReconstructionWorkflow(caller).reconstruct(
        prepared,
        observations,
        bundle,
    )

    assert result.attempts == 1
    assert result.diagram.annotations == []
    assert result.diagram.limitations == [
        "Omitted 1 annotation whose text was not literally visible in cited evidence."
    ]
    assert len(caller.calls) == 1


def test_reconstruction_prompts_distinguish_object_containment_from_groups() -> None:
    initial = build_reconstruction_prompt()
    repair = build_reconstruction_repair_prompt("candidate-0001", "{}", "{}", "finding")

    assert "parent_id may name only another analyzed object" in initial
    assert "never a group ID" in repair
    assert "groups[].object_ids" in initial
    assert "groups[].object_ids" in repair


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


def test_observation_failure_preserves_both_attempts_and_validation_error(
    tmp_path: Path,
) -> None:
    prepared, bundle = _prepared_bundle(tmp_path)

    with pytest.raises(ObservationWorkflowError) as caught:
        StructuredObservationWorkflow(
            FakeImageCall([_observation_response(evidence_id="missing")] * 2)
        ).observe(prepared, bundle)

    assert len(caught.value.traces) == 2
    assert "missing" in caught.value.traces[-1].raw_response
    assert "unknown evidence" in (caught.value.validation_error or "")


def test_semantic_pipeline_never_calls_beyond_configured_budget(tmp_path: Path) -> None:
    prepared, bundle = _prepared_bundle(tmp_path)
    observation_call = FakeImageCall(
        [_observation_response(evidence_id="missing"), _observation_response()]
    )
    reconstruction_call = FakeImageCall([_diagram_response(label="Invented")])
    workflow = SemanticAnalysisWorkflow(
        StructuredObservationWorkflow(observation_call),
        StructuredReconstructionWorkflow(reconstruction_call),
        limits=DocumentSafetyLimits(max_model_calls_per_candidate=3),
    )

    with pytest.raises(SemanticAnalysisWorkflowError) as captured:
        workflow.analyze(prepared, bundle)

    assert len(observation_call.calls) == 2
    assert len(reconstruction_call.calls) == 1
    assert captured.value.stage == "reconstruction"
    assert len(captured.value.traces) == 3


def test_semantic_pipeline_rejects_impossible_budget_before_provider_call(
    tmp_path: Path,
) -> None:
    prepared, bundle = _prepared_bundle(tmp_path)
    observation_call = FakeImageCall([_observation_response()])
    reconstruction_call = FakeImageCall([_diagram_response()])
    workflow = SemanticAnalysisWorkflow(
        StructuredObservationWorkflow(observation_call),
        StructuredReconstructionWorkflow(reconstruction_call),
        limits=DocumentSafetyLimits(max_model_calls_per_candidate=1),
    )

    with pytest.raises(RuntimeError, match="at least two"):
        workflow.analyze(prepared, bundle)

    assert observation_call.calls == []
    assert reconstruction_call.calls == []
