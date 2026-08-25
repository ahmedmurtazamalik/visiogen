"""Strict A5 contracts for selected prose, atomic claims, and entity alignment."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from visiogen.analysis.models import AnalysisModel, Confidence
from visiogen.documents.models import SourceLocation, TextOrigin

SelectionReason = Literal[
    "asset_anchor",
    "caption",
    "figure_reference",
    "proximity",
    "label_match",
    "reference_match",
    "explicit",
]
ClaimPredicate = Literal[
    "exists",
    "not_exists",
    "alias",
    "type_or_role",
    "contains",
    "connects_to",
    "direction",
    "relationship_type",
    "branch_condition",
    "cardinality",
    "reference_mapping",
    "sequence",
    "attribute_or_state",
    "figure_title",
    "figure_purpose",
]
ClaimModality = Literal[
    "asserted",
    "required",
    "possible",
    "example",
    "negated",
    "unknown",
]
ClaimScope = Literal["current_figure", "document", "section", "example", "unknown"]
FigureReference = Literal["yes", "no", "unclear"]
EntityRole = Literal["subject", "object"]
AlignmentMethod = Literal[
    "exact_reference",
    "exact_label",
    "explicit_alias",
    "conservative_fuzzy",
    "model_assisted",
    "unresolved",
]


class SelectedTextBlock(AnalysisModel):
    """Exact bounded source block selected mechanically for one candidate."""

    block_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    origin: TextOrigin
    order: int = Field(ge=0)
    location: SourceLocation
    reasons: list[SelectionReason] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reasons(self) -> SelectedTextBlock:
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("Selected-text reasons must be unique")
        return self


class TextSelection(AnalysisModel):
    """Complete bounded passage selection with explicit skipped-block accounting."""

    source_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    blocks: list[SelectedTextBlock]
    omitted_block_ids: list[str] = Field(default_factory=list)
    max_blocks: int = Field(gt=0)
    max_characters: int = Field(gt=0)
    selected_characters: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_selection(self) -> TextSelection:
        block_ids = [item.block_id for item in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("Selected text block IDs must be unique")
        if len(self.omitted_block_ids) != len(set(self.omitted_block_ids)):
            raise ValueError("Omitted text block IDs must be unique")
        if set(block_ids) & set(self.omitted_block_ids):
            raise ValueError("A text block cannot be both selected and omitted")
        if len(self.blocks) > self.max_blocks:
            raise ValueError("Selected text exceeds its block limit")
        if sum(len(item.text) for item in self.blocks) != self.selected_characters:
            raise ValueError("Selected character count does not match selected blocks")
        if self.selected_characters > self.max_characters:
            raise ValueError("Selected text exceeds its character limit")
        return self


class TextClaimEvidence(AnalysisModel):
    """Exact model-cited span within one selected text block."""

    id: str = Field(pattern=r"^text-evidence-[0-9]{4}$")
    block_id: str = Field(min_length=1)
    exact_text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> TextClaimEvidence:
        if self.end <= self.start:
            raise ValueError("Text evidence end must follow start")
        return self


class DocumentClaim(AnalysisModel):
    """One atomic proposition extracted independently from selected document prose."""

    id: str = Field(pattern=r"^claim-[0-9]{4}$")
    subject_text: str = Field(min_length=1)
    normalized_subject: str = Field(min_length=1)
    predicate: ClaimPredicate
    object_text: str | None = None
    normalized_object: str | None = None
    modality: ClaimModality
    scope: ClaimScope
    qualifiers: list[str] = Field(default_factory=list)
    exhaustive: bool = False
    refers_to_candidate: FigureReference
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    ambiguity: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_claim(self) -> DocumentClaim:
        if (self.object_text is None) != (self.normalized_object is None):
            raise ValueError("Claim object text and normalization must be supplied together")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Claim evidence IDs must be unique")
        return self


class DocumentClaimBatch(AnalysisModel):
    """Untrusted structured claim response before evidence validation."""

    candidate_id: str = Field(min_length=1)
    evidence: list[TextClaimEvidence]
    claims: list[DocumentClaim]
    warnings: list[str] = Field(default_factory=list)


class AlignmentAlternative(AnalysisModel):
    """One plausible object match retained when alignment is not decisive."""

    object_id: str = Field(min_length=1)
    method: AlignmentMethod
    score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class EntityAlignment(AnalysisModel):
    """Auditable alignment of one claim entity to zero or one diagram object."""

    claim_id: str = Field(min_length=1)
    entity_role: EntityRole
    entity_text: str = Field(min_length=1)
    normalized_entity: str = Field(min_length=1)
    object_id: str | None = None
    method: AlignmentMethod
    score: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1)
    alternatives: list[AlignmentAlternative] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_resolution(self) -> EntityAlignment:
        if self.method == "unresolved" and self.object_id is not None:
            raise ValueError("Unresolved alignments cannot select an object")
        if self.method != "unresolved" and self.object_id is None:
            raise ValueError("Resolved alignments require an object")
        return self


class EntityAlignmentSet(AnalysisModel):
    """All subject/object alignments for one candidate's claim batch."""

    candidate_id: str = Field(min_length=1)
    alignments: list[EntityAlignment]

    @model_validator(mode="after")
    def validate_alignments(self) -> EntityAlignmentSet:
        keys = [(item.claim_id, item.entity_role) for item in self.alignments]
        if len(keys) != len(set(keys)):
            raise ValueError("Claim entity alignments must be unique")
        return self
