"""Strict A3 contracts for visual observations and semantic reconstruction."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from visiogen.analysis.models import AnalysisModel, Confidence
from visiogen.documents.models import NormalizedBox

ObservationKind = Literal[
    "visible_text",
    "object",
    "container",
    "connector",
    "arrowhead",
    "legend",
    "note",
    "callout",
    "grouping",
]
DiagramFamily = Literal[
    "flowchart",
    "system_block",
    "component_schematic",
    "state_machine",
    "network",
    "data_flow",
    "sequence_like",
    "unknown",
]
DiagramOrientation = Literal[
    "left_to_right",
    "right_to_left",
    "top_to_bottom",
    "bottom_to_top",
    "radial",
    "mixed",
    "unknown",
]
EndpointCertainty = Literal["known", "ambiguous", "dangling", "not_visible"]
RelationshipDirection = Literal[
    "forward",
    "reverse",
    "bidirectional",
    "none",
    "unclear",
]
RelationshipKind = Literal[
    "flow",
    "data",
    "control",
    "power",
    "communication",
    "mechanical",
    "association",
    "unknown",
]


class NormalizedPoint(AnalysisModel):
    """Top-left-origin point in normalized image coordinates."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class InterpretationAlternative(AnalysisModel):
    """One plausible competing reading retained instead of silently discarded."""

    value: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    confidence: Confidence


class ObservedProperty(AnalysisModel):
    """One visible property expressed without an open-ended JSON object."""

    name: str = Field(min_length=1)
    value: str = Field(min_length=1)


class RawImageEvidence(AnalysisModel):
    """Model-returned region local to one supplied overview or tile."""

    id: str = Field(pattern=r"^evidence-[0-9]{4}$")
    derivative_id: str = Field(min_length=1)
    local_bbox: NormalizedBox


class VisualEvidence(RawImageEvidence):
    """Validated evidence with a deterministic source-image coordinate transform."""

    source_bbox: NormalizedBox


class RawVisualObservation(AnalysisModel):
    """One model-returned visible mark in one derivative's local coordinates."""

    id: str = Field(pattern=r"^observation-[0-9]{4}$")
    kind: ObservationKind
    geometry_derivative_id: str = Field(min_length=1)
    local_bbox: NormalizedBox | None = None
    local_path: list[NormalizedPoint] = Field(default_factory=list)
    visible_text: str | None = None
    properties: list[ObservedProperty] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    alternatives: list[InterpretationAlternative] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_visible_content(self) -> RawVisualObservation:
        if self.local_bbox is None and not self.local_path:
            raise ValueError("Visual observation requires a bounding box or path")
        if self.kind == "visible_text" and not (self.visible_text or "").strip():
            raise ValueError("Visible-text observations require exact visible_text")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Observation evidence IDs must be unique")
        return self


class VisualObservation(AnalysisModel):
    """Literal visible mark transformed into source-image coordinates by code."""

    id: str = Field(pattern=r"^observation-[0-9]{4}$")
    kind: ObservationKind
    source_bbox: NormalizedBox | None = None
    source_path: list[NormalizedPoint] = Field(default_factory=list)
    visible_text: str | None = None
    properties: list[ObservedProperty] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    alternatives: list[InterpretationAlternative] = Field(default_factory=list)


class RawObservationBatch(AnalysisModel):
    """Strict untrusted output from the image-only observation call."""

    candidate_id: str = Field(min_length=1)
    evidence: list[RawImageEvidence]
    observations: list[RawVisualObservation]
    warnings: list[str] = Field(default_factory=list)


class ValidatedObservationSet(AnalysisModel):
    """Observation result after reference checks and coordinate transformation."""

    candidate_id: str = Field(min_length=1)
    evidence: list[VisualEvidence]
    observations: list[VisualObservation]
    warnings: list[str] = Field(default_factory=list)


class AnalyzedObject(AnalysisModel):
    """One interpreted diagram object bound to literal visual evidence."""

    id: str = Field(pattern=r"^object-[0-9]{4}$")
    visible_label: str | None = None
    normalized_label: str | None = None
    semantic_type: str = Field(min_length=1)
    visual_shape: str = Field(min_length=1)
    reference_numbers: list[str] = Field(default_factory=list)
    parent_id: str | None = Field(
        default=None,
        description=(
            "ID of another analyzed object that visibly contains this object; never a group ID"
        ),
    )
    bbox: NormalizedBox
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    alternatives: list[InterpretationAlternative] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_label_pair(self) -> AnalyzedObject:
        if (self.visible_label is None) != (self.normalized_label is None):
            raise ValueError("Visible and normalized object labels must be supplied together")
        if len(self.reference_numbers) != len(set(self.reference_numbers)):
            raise ValueError("Object reference numbers must be unique")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Object evidence IDs must be unique")
        return self


class AnalyzedRelationship(AnalysisModel):
    """One interpreted connector with explicit endpoint uncertainty."""

    id: str = Field(pattern=r"^relationship-[0-9]{4}$")
    source_id: str | None = None
    target_id: str | None = None
    source_certainty: EndpointCertainty
    target_certainty: EndpointCertainty
    direction: RelationshipDirection
    relation: RelationshipKind
    visible_label: str | None = None
    normalized_label: str | None = None
    path: list[NormalizedPoint] = Field(default_factory=list)
    line_style: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    alternatives: list[InterpretationAlternative] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_relationship(self) -> AnalyzedRelationship:
        if (self.visible_label is None) != (self.normalized_label is None):
            raise ValueError("Visible and normalized relationship labels must be supplied together")
        if self.source_certainty == "known" and self.source_id is None:
            raise ValueError("Known relationship source requires source_id")
        if self.target_certainty == "known" and self.target_id is None:
            raise ValueError("Known relationship target requires target_id")
        if self.direction == "unclear" and self.confidence == "high":
            raise ValueError("Unclear relationship direction cannot have high confidence")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Relationship evidence IDs must be unique")
        return self


class AnalyzedGroup(AnalysisModel):
    """One visually supported group, lane, zone, or container."""

    id: str = Field(pattern=r"^group-[0-9]{4}$")
    kind: str = Field(min_length=1)
    visible_label: str | None = None
    object_ids: list[str] = Field(default_factory=list)
    bbox: NormalizedBox
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence

    @model_validator(mode="after")
    def validate_references(self) -> AnalyzedGroup:
        if len(self.object_ids) != len(set(self.object_ids)):
            raise ValueError("Group object IDs must be unique")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Group evidence IDs must be unique")
        return self


class LegendMapping(AnalysisModel):
    """One visible legend symbol-to-meaning mapping."""

    symbol: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence

    @model_validator(mode="after")
    def validate_evidence(self) -> LegendMapping:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Legend evidence IDs must be unique")
        return self


class DiagramAnnotation(AnalysisModel):
    """One visible note or callout retained as first-class diagram evidence."""

    id: str = Field(pattern=r"^annotation-[0-9]{4}$")
    kind: Literal["note", "callout"]
    visible_text: str = Field(min_length=1)
    attached_object_ids: list[str] = Field(default_factory=list)
    bbox: NormalizedBox
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    alternatives: list[InterpretationAlternative] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> DiagramAnnotation:
        if len(self.attached_object_ids) != len(set(self.attached_object_ids)):
            raise ValueError("Annotation attached object IDs must be unique")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Annotation evidence IDs must be unique")
        return self


class AnalyzedDiagram(AnalysisModel):
    """Evidence-grounded semantic reconstruction of one selected candidate."""

    candidate_id: str = Field(min_length=1)
    title: str | None = None
    title_evidence_ids: list[str] = Field(default_factory=list)
    family: DiagramFamily
    orientation: DiagramOrientation
    objects: list[AnalyzedObject]
    relationships: list[AnalyzedRelationship]
    groups: list[AnalyzedGroup] = Field(default_factory=list)
    legends: list[LegendMapping] = Field(default_factory=list)
    annotations: list[DiagramAnnotation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: Confidence

    @model_validator(mode="after")
    def validate_title_evidence(self) -> AnalyzedDiagram:
        if self.title is None and self.title_evidence_ids:
            raise ValueError("Untitled diagrams cannot cite title evidence")
        if self.title is not None and not self.title_evidence_ids:
            raise ValueError("Visible diagram titles require evidence")
        return self
