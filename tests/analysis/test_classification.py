"""Structured multimodal candidate-classifier contract tests."""

import json
from pathlib import Path

import pytest

from visiogen.analysis.classification import StructuredCandidateClassifier
from visiogen.analysis.errors import CandidateClassificationError
from visiogen.analysis.models import CandidateDecision, DiagramCandidate
from visiogen.providers.base import ProviderResponse


def _candidate() -> DiagramCandidate:
    decision = CandidateDecision(
        candidate_id="candidate-0001",
        label="unknown",
        confidence="unknown",
        reason="Visual classification required",
        classifier="mechanical-enumeration-v1",
    )
    return DiagramCandidate(
        id="candidate-0001",
        primary_asset_id="asset-1",
        source_asset_ids=["asset-1"],
        page_number=2,
        width_px=1200,
        height_px=800,
        decision=decision,
        disposition="awaiting_classification",
        disposition_reason=decision.reason,
    )


class RecordingImageCall:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = []

    def call_with_images(self, system_prompt, user_prompt, images):
        self.calls.append((system_prompt, user_prompt, list(images)))
        return ProviderResponse(content=self.content, elapsed_ms=12)


def test_structured_classifier_binds_images_ids_regions_and_identity(tmp_path: Path) -> None:
    image = tmp_path / "candidate.png"
    image.write_bytes(b"image input")
    response = json.dumps(
        {
            "decisions": [
                {
                    "candidate_id": "candidate-0001",
                    "label": "diagram",
                    "confidence": "high",
                    "reason": "Visible connected process boxes",
                    "region": {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.8},
                }
            ]
        }
    )
    caller = RecordingImageCall(response)
    classifier = StructuredCandidateClassifier(
        caller,
        {"candidate-0001": image},
        classifier_identity="fake-vision/model-v1",
    )

    decisions = classifier.classify((_candidate(),))

    assert decisions[0].label == "diagram"
    assert decisions[0].classifier == "fake-vision/model-v1"
    assert decisions[0].region is not None
    system_prompt, user_prompt, images = caller.calls[0]
    assert "Photographs, charts/plots" in system_prompt
    assert "candidate-0001" in user_prompt
    assert images == [image]


def test_structured_classifier_rejects_missing_or_duplicate_decisions(tmp_path: Path) -> None:
    image = tmp_path / "candidate.png"
    image.write_bytes(b"image input")
    caller = RecordingImageCall('{"decisions": []}')
    classifier = StructuredCandidateClassifier(
        caller,
        {"candidate-0001": image},
        classifier_identity="fake",
    )

    with pytest.raises(CandidateClassificationError, match="exactly"):
        classifier.classify((_candidate(),))
