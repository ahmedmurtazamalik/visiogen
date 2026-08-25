"""Strict multimodal classification of mechanically enumerated candidates."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from pydantic import Field, ValidationError

from visiogen.analysis.errors import CandidateClassificationError
from visiogen.analysis.models import (
    AnalysisModel,
    CandidateDecision,
    CandidateLabel,
    Confidence,
    DiagramCandidate,
)
from visiogen.documents.models import NormalizedBox
from visiogen.providers.base import ImageStructuredCall


class VisualCandidateDecision(AnalysisModel):
    """Provider output for one supplied image, before trusted metadata is injected."""

    candidate_id: str = Field(min_length=1)
    label: CandidateLabel
    confidence: Confidence
    reason: str = Field(min_length=1)
    region: NormalizedBox | None = None


class VisualCandidateBatch(AnalysisModel):
    """Complete structured classification response for one bounded batch."""

    decisions: list[VisualCandidateDecision]


class CandidateClassificationTrace(AnalysisModel):
    """Exact model-call evidence retained for acceptance and later provenance."""

    classifier_identity: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    transport_prompt: str | None = None
    raw_response: str = Field(min_length=1)
    elapsed_ms: float = Field(ge=0)
    image_sha256: dict[str, str]


def build_candidate_classification_prompt() -> str:
    """Return the stable logical instruction for diagram discovery."""

    schema = json.dumps(VisualCandidateBatch.model_json_schema(), sort_keys=True)
    return (
        "Classify each supplied document image independently. A diagram is a flowchart, "
        "system or software architecture, process map, network topology, component schematic, "
        "or another visual whose boxes, symbols, containers, and connectors encode relationships. "
        "Photographs, charts/plots, tables, equations, logos, decorative art, and ordinary UI "
        "screenshots are non_diagram. Use unknown when resolution or mixed content prevents a "
        "defensible classification. Never infer a diagram solely from nearby prose. For a diagram "
        "embedded within a larger page, return its tight normalized top-left-origin region; "
        "use null "
        "for the full image or when no defensible region exists. Confidence is high only for clear "
        "direct visual evidence, medium when a plausible alternative remains, low for tentative "
        "classification, and unknown only with label unknown. Return one decision for every listed "
        "candidate and do not include unlisted IDs. Return JSON only. "
        f"The response must satisfy this JSON Schema: {schema}"
    )


class StructuredCandidateClassifier:
    """Validate one structured multimodal classification call."""

    def __init__(
        self,
        call_model: ImageStructuredCall,
        image_by_candidate_id: dict[str, str | Path],
        *,
        classifier_identity: str,
    ) -> None:
        self._call_model = call_model
        self._images = {key: Path(value) for key, value in image_by_candidate_id.items()}
        self._identity = classifier_identity
        self._last_trace: CandidateClassificationTrace | None = None

    @property
    def last_trace(self) -> CandidateClassificationTrace | None:
        """Return exact evidence from the most recent successful call."""

        return self._last_trace

    def classify(
        self,
        candidates: tuple[DiagramCandidate, ...],
    ) -> tuple[CandidateDecision, ...]:
        candidate_ids = [candidate.id for candidate in candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise CandidateClassificationError("Classifier input contains duplicate IDs")
        missing = [
            candidate_id
            for candidate_id in candidate_ids
            if candidate_id not in self._images
        ]
        if missing:
            raise CandidateClassificationError(
                f"Classifier image mapping is incomplete: {', '.join(missing)}"
            )
        image_paths = [self._images[candidate_id] for candidate_id in candidate_ids]
        if any(not path.is_file() for path in image_paths):
            raise CandidateClassificationError("A candidate classifier image was not found")
        user_prompt = (
            "Images are attached in this exact order:\n"
            + "\n".join(
                f"{index}. {candidate.id} ({candidate.width_px}x{candidate.height_px}, "
                f"page={candidate.page_number or 'unknown'})"
                for index, candidate in enumerate(candidates, start=1)
            )
        )
        system_prompt = build_candidate_classification_prompt()
        try:
            response = self._call_model.call_with_images(
                system_prompt,
                user_prompt,
                image_paths,
            )
            batch = VisualCandidateBatch.model_validate_json(response.content)
        except ValidationError as error:
            raise CandidateClassificationError(
                "Candidate classifier returned invalid structured output"
            ) from error
        except CandidateClassificationError:
            raise
        except Exception as error:
            raise CandidateClassificationError("Candidate classifier call failed") from error

        returned = [decision.candidate_id for decision in batch.decisions]
        if len(returned) != len(set(returned)) or set(returned) != set(candidate_ids):
            raise CandidateClassificationError(
                "Candidate classifier must return exactly the supplied candidate IDs"
            )
        by_id = {decision.candidate_id: decision for decision in batch.decisions}
        decisions: list[CandidateDecision] = []
        for candidate_id in candidate_ids:
            decision = by_id[candidate_id]
            try:
                decisions.append(
                    CandidateDecision(
                        candidate_id=candidate_id,
                        label=decision.label,
                        confidence=decision.confidence,
                        reason=decision.reason,
                        classifier=self._identity,
                        region=decision.region,
                    )
                )
            except ValidationError as error:
                raise CandidateClassificationError(
                    f"Candidate classifier decision is inconsistent: {candidate_id}"
                ) from error
        self._last_trace = CandidateClassificationTrace(
            classifier_identity=self._identity,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            transport_prompt=response.transport_prompt,
            raw_response=response.content,
            elapsed_ms=response.elapsed_ms or 0,
            image_sha256={
                candidate_id: hashlib.sha256(path.read_bytes()).hexdigest()
                for candidate_id, path in zip(candidate_ids, image_paths, strict=True)
            },
        )
        return tuple(decisions)
