"""Strict contracts for diagram candidate discovery and image preparation."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from visiogen.documents.models import NormalizedBox

Confidence = Literal["high", "medium", "low", "unknown"]
CandidateLabel = Literal["diagram", "non_diagram", "unknown"]
CandidateDisposition = Literal[
    "selected",
    "ignored_non_diagram",
    "awaiting_classification",
    "filtered_out",
    "skipped_limit",
]
DerivativeKind = Literal["crop", "overview", "tile"]
DuplicateMethod = Literal["exact_sha256", "embedded_page_visual_v1"]


class AnalysisModel(BaseModel):
    """Strict base for analysis-owned records."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CandidateDecision(AnalysisModel):
    """One evidence-bound classification supplied mechanically or by a classifier."""

    candidate_id: str = Field(min_length=1)
    label: CandidateLabel
    confidence: Confidence
    reason: str = Field(min_length=1)
    classifier: str = Field(min_length=1)
    region: NormalizedBox | None = None

    @model_validator(mode="after")
    def validate_unknown_confidence(self) -> CandidateDecision:
        if self.label == "unknown" and self.confidence != "unknown":
            raise ValueError("Unknown candidate labels require unknown confidence")
        if self.label != "diagram" and self.region is not None:
            raise ValueError("Only diagram candidates may define a crop region")
        return self


class DuplicateMatch(AnalysisModel):
    """Auditable reason that two assets represent the same candidate."""

    first_asset_id: str = Field(min_length=1)
    second_asset_id: str = Field(min_length=1)
    method: DuplicateMethod
    similarity: float = Field(ge=0, le=1)
    page_region: NormalizedBox | None = None

    @model_validator(mode="after")
    def validate_distinct_assets(self) -> DuplicateMatch:
        if self.first_asset_id == self.second_asset_id:
            raise ValueError("Duplicate evidence must reference two distinct assets")
        if self.method == "exact_sha256" and self.similarity != 1:
            raise ValueError("Exact duplicate evidence requires similarity 1")
        if self.method == "exact_sha256" and self.page_region is not None:
            raise ValueError("Exact duplicate evidence does not define a page region")
        return self


class DiagramCandidate(AnalysisModel):
    """One unique visual candidate and the explicit reason for its disposition."""

    id: str = Field(pattern=r"^candidate-[0-9]{4}$")
    primary_asset_id: str = Field(min_length=1)
    source_asset_ids: list[str] = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    duplicate_matches: list[DuplicateMatch] = Field(default_factory=list)
    decision: CandidateDecision
    disposition: CandidateDisposition
    disposition_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate(self) -> DiagramCandidate:
        if self.primary_asset_id not in self.source_asset_ids:
            raise ValueError("Primary candidate asset must appear in source_asset_ids")
        if len(self.source_asset_ids) != len(set(self.source_asset_ids)):
            raise ValueError("Candidate source asset IDs must be unique")
        source_ids = set(self.source_asset_ids)
        for match in self.duplicate_matches:
            if {match.first_asset_id, match.second_asset_id} - source_ids:
                raise ValueError("Duplicate evidence must stay within the candidate asset group")
        if self.decision.candidate_id != self.id:
            raise ValueError("Candidate decision ID must match its candidate")
        expected = {
            "ignored_non_diagram": "non_diagram",
            "awaiting_classification": "unknown",
        }
        if self.disposition in expected and self.decision.label != expected[self.disposition]:
            raise ValueError("Candidate disposition does not match its classification")
        if self.disposition == "selected" and self.decision.label == "non_diagram":
            raise ValueError("A known non-diagram candidate cannot be selected")
        return self


class CandidateCoverage(AnalysisModel):
    """Counts proving that every enumerated asset received a disposition."""

    source_assets: int = Field(ge=0)
    unique_candidates: int = Field(ge=0)
    duplicate_assets_grouped: int = Field(ge=0)
    selected: int = Field(ge=0)
    ignored_non_diagram: int = Field(ge=0)
    awaiting_classification: int = Field(ge=0)
    filtered_out: int = Field(ge=0)
    skipped_limit: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_totals(self) -> CandidateCoverage:
        dispositions = (
            self.selected
            + self.ignored_non_diagram
            + self.awaiting_classification
            + self.filtered_out
            + self.skipped_limit
        )
        if dispositions != self.unique_candidates:
            raise ValueError("Candidate coverage dispositions must cover every candidate")
        if self.source_assets - self.unique_candidates != self.duplicate_assets_grouped:
            raise ValueError("Duplicate coverage count does not match enumerated assets")
        return self


class CandidateDiscovery(AnalysisModel):
    """Stable discovery result before expensive visual reconstruction."""

    source_id: str = Field(min_length=1)
    candidates: list[DiagramCandidate] = Field(default_factory=list)
    coverage: CandidateCoverage

    @model_validator(mode="after")
    def validate_candidates(self) -> CandidateDiscovery:
        ids = [candidate.id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Candidate IDs must be unique")
        if len(self.candidates) != self.coverage.unique_candidates:
            raise ValueError("Candidate list does not match coverage")
        return self


class PreparedDerivative(AnalysisModel):
    """One checksum-bound image prepared for a later multimodal model call."""

    id: str = Field(min_length=1)
    kind: DerivativeKind
    artifact_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(gt=0)
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    source_region: NormalizedBox

    @model_validator(mode="after")
    def validate_path(self) -> PreparedDerivative:
        path = PurePosixPath(self.artifact_path)
        if "\\" in self.artifact_path or path.is_absolute() or ".." in path.parts:
            raise ValueError("Prepared artifact path must remain inside the bundle")
        return self


class PreparedCandidate(AnalysisModel):
    """Crop, overview, and bounded tiles for one selected candidate."""

    candidate_id: str = Field(min_length=1)
    derivatives: list[PreparedDerivative] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_derivatives(self) -> PreparedCandidate:
        ids = [derivative.id for derivative in self.derivatives]
        if len(ids) != len(set(ids)):
            raise ValueError("Prepared derivative IDs must be unique")
        kinds = [derivative.kind for derivative in self.derivatives]
        if kinds.count("crop") != 1 or kinds.count("overview") != 1:
            raise ValueError("Prepared candidates require one crop and one overview")
        return self


class CandidatePreparation(AnalysisModel):
    """Published A2 bundle manifest."""

    discovery: CandidateDiscovery
    prepared_candidates: list[PreparedCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_prepared_candidates(self) -> CandidatePreparation:
        selected = {
            candidate.id
            for candidate in self.discovery.candidates
            if candidate.disposition == "selected"
        }
        prepared = [candidate.candidate_id for candidate in self.prepared_candidates]
        if len(prepared) != len(set(prepared)):
            raise ValueError("Prepared candidate IDs must be unique")
        if set(prepared) != selected:
            raise ValueError("Every selected candidate must be prepared exactly once")
        return self
