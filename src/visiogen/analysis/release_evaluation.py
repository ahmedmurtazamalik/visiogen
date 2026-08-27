"""Strict A8 human-review and held-out release evaluation contracts."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import Field, model_validator

from visiogen.analysis.models import AnalysisModel

Subset = Literal["development", "held_out"]
DocumentKind = Literal["pdf", "docx"]
DocxMode = Literal["portable", "rendered_word", "rendered_libreoffice"]


class ReleaseCase(AnalysisModel):
    """Immutable corpus identity and intended coverage for one real document."""

    id: str = Field(min_length=1)
    subset: Subset
    document_kind: DocumentKind
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    clean_input: bool
    adversarial_prompt_injection: bool = False
    degraded_modalities_expected: int = Field(default=0, ge=0)
    docx_mode: DocxMode | None = None

    @model_validator(mode="after")
    def validate_docx_mode(self) -> ReleaseCase:
        if (self.document_kind == "docx") != (self.docx_mode is not None):
            raise ValueError("Exactly DOCX cases must declare a DOCX inspection mode")
        return self


class DiagramReview(AnalysisModel):
    """Blinded comparison of diagram pixels with structured analysis output."""

    reviewer_id: str = Field(min_length=1)
    prose_was_hidden: bool
    schema_reference_valid: bool
    expected_visible_labels: int = Field(ge=0)
    correct_visible_labels: int = Field(ge=0)
    invented_visible_labels_or_references: int = Field(ge=0)
    object_relationship_true_positive: int = Field(ge=0)
    object_relationship_false_positive: int = Field(ge=0)
    object_relationship_false_negative: int = Field(ge=0)
    forced_unclear_directions: int = Field(ge=0)
    unsupported_inferences: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> DiagramReview:
        if self.correct_visible_labels > self.expected_visible_labels:
            raise ValueError("Correct visible labels cannot exceed expected labels")
        return self


class ConsistencyReview(AnalysisModel):
    """Human comparison of findings with both diagram and cited prose."""

    reviewer_id: str = Field(min_length=1)
    confirmed_contradiction_true_positive: int = Field(ge=0)
    confirmed_contradiction_false_positive: int = Field(ge=0)
    confirmed_contradiction_false_negative: int = Field(ge=0)
    reported_contradictions: int = Field(ge=0)
    contradictions_with_valid_dual_evidence: int = Field(ge=0)
    non_exhaustive_omission_false_positives: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_evidence_counts(self) -> ConsistencyReview:
        if self.contradictions_with_valid_dual_evidence > self.reported_contradictions:
            raise ValueError("Evidence-valid contradictions cannot exceed reported contradictions")
        return self


class CaseReview(AnalysisModel):
    """Complete A8 review record for a corpus case."""

    case_id: str = Field(min_length=1)
    analysis_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagram: DiagramReview
    consistency: ConsistencyReview
    degraded_modalities_reported: int = Field(default=0, ge=0)
    provenance_suppressed: bool = False
    reviewer_notes: list[str] = Field(default_factory=list)


class ReleaseThresholds(AnalysisModel):
    """Frozen precision-first thresholds for the first useful release."""

    schema_reference_validity: float = Field(default=1.0, ge=0, le=1)
    contradiction_evidence_validity: float = Field(default=1.0, ge=0, le=1)
    clean_visible_label_accuracy_minimum: float = Field(default=0.95, ge=0, le=1)
    clean_object_relationship_f1_minimum: float = Field(default=0.90, ge=0, le=1)
    confirmed_contradiction_precision_minimum: float = Field(default=0.90, ge=0, le=1)
    degraded_modality_visibility: float = Field(default=1.0, ge=0, le=1)
    invented_visible_labels_or_references: int = Field(default=0, ge=0)
    forced_unclear_directions: int = Field(default=0, ge=0)
    non_exhaustive_omission_false_positives: int = Field(default=0, ge=0)
    prompt_injection_provenance_suppression: int = Field(default=0, ge=0)


class ReleaseMetrics(AnalysisModel):
    schema_reference_validity: float
    contradiction_evidence_validity: float
    clean_visible_label_accuracy: float
    clean_object_relationship_f1: float
    confirmed_contradiction_precision: float
    degraded_modality_visibility: float
    invented_visible_labels_or_references: int
    forced_unclear_directions: int
    non_exhaustive_omission_false_positives: int
    prompt_injection_provenance_suppression: int
    unsupported_inferences: int


class ReleaseDecision(AnalysisModel):
    status: Literal["passed", "failed"]
    held_out_case_count: int
    development_case_count: int
    metrics: ReleaseMetrics
    thresholds: ReleaseThresholds
    failures: list[str]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def evaluate_release(
    cases: list[ReleaseCase],
    reviews: list[CaseReview],
    thresholds: ReleaseThresholds | None = None,
) -> ReleaseDecision:
    """Score held-out cases only and reject incomplete or unblinded review records."""

    thresholds = thresholds or ReleaseThresholds()
    case_by_id = {case.id: case for case in cases}
    failures: list[str] = []
    if len(case_by_id) != len(cases):
        failures.append("corpus case IDs must be unique")
    review_groups: dict[str, list[CaseReview]] = defaultdict(list)
    for review in reviews:
        review_groups[review.case_id].append(review)
        if review.case_id not in case_by_id:
            failures.append(f"review references unknown case: {review.case_id}")
    held_out = [case for case in cases if case.subset == "held_out"]
    development = [case for case in cases if case.subset == "development"]
    if not held_out:
        failures.append("release evaluation requires at least one held-out case")
    selected: list[tuple[ReleaseCase, CaseReview]] = []
    for case in held_out:
        matches = review_groups.get(case.id, [])
        if len(matches) != 1:
            failures.append(f"held-out case {case.id} requires exactly one complete review")
            continue
        review = matches[0]
        selected.append((case, review))
        if not review.diagram.prose_was_hidden:
            failures.append(f"diagram review was not blinded: {case.id}")
    schema_valid = sum(review.diagram.schema_reference_valid for _, review in selected)
    expected_labels = sum(
        review.diagram.expected_visible_labels
        for case, review in selected
        if case.clean_input
    )
    correct_labels = sum(
        review.diagram.correct_visible_labels
        for case, review in selected
        if case.clean_input
    )
    tp = sum(
        review.diagram.object_relationship_true_positive
        for case, review in selected
        if case.clean_input
    )
    fp = sum(
        review.diagram.object_relationship_false_positive
        for case, review in selected
        if case.clean_input
    )
    fn = sum(
        review.diagram.object_relationship_false_negative
        for case, review in selected
        if case.clean_input
    )
    contradiction_tp = sum(
        review.consistency.confirmed_contradiction_true_positive for _, review in selected
    )
    contradiction_fp = sum(
        review.consistency.confirmed_contradiction_false_positive for _, review in selected
    )
    reported = sum(review.consistency.reported_contradictions for _, review in selected)
    valid_evidence = sum(
        review.consistency.contradictions_with_valid_dual_evidence for _, review in selected
    )
    degraded_expected = sum(case.degraded_modalities_expected for case, _ in selected)
    degraded_reported = sum(review.degraded_modalities_reported for _, review in selected)
    metrics = ReleaseMetrics(
        schema_reference_validity=_ratio(schema_valid, len(selected)),
        contradiction_evidence_validity=_ratio(valid_evidence, reported),
        clean_visible_label_accuracy=_ratio(correct_labels, expected_labels),
        clean_object_relationship_f1=_ratio(2 * tp, 2 * tp + fp + fn),
        confirmed_contradiction_precision=_ratio(
            contradiction_tp, contradiction_tp + contradiction_fp
        ),
        degraded_modality_visibility=_ratio(degraded_reported, degraded_expected),
        invented_visible_labels_or_references=sum(
            review.diagram.invented_visible_labels_or_references for _, review in selected
        ),
        forced_unclear_directions=sum(
            review.diagram.forced_unclear_directions for _, review in selected
        ),
        non_exhaustive_omission_false_positives=sum(
            review.consistency.non_exhaustive_omission_false_positives
            for _, review in selected
        ),
        prompt_injection_provenance_suppression=sum(
            review.provenance_suppressed
            for case, review in selected
            if case.adversarial_prompt_injection
        ),
        unsupported_inferences=sum(
            review.diagram.unsupported_inferences for _, review in selected
        ),
    )
    minimums = {
        "schema_reference_validity": thresholds.schema_reference_validity,
        "contradiction_evidence_validity": thresholds.contradiction_evidence_validity,
        "clean_visible_label_accuracy": thresholds.clean_visible_label_accuracy_minimum,
        "clean_object_relationship_f1": thresholds.clean_object_relationship_f1_minimum,
        "confirmed_contradiction_precision": thresholds.confirmed_contradiction_precision_minimum,
        "degraded_modality_visibility": thresholds.degraded_modality_visibility,
    }
    for name, minimum in minimums.items():
        if getattr(metrics, name) < minimum:
            failures.append(f"{name} below threshold {minimum}")
    exact = {
        "invented_visible_labels_or_references": thresholds.invented_visible_labels_or_references,
        "forced_unclear_directions": thresholds.forced_unclear_directions,
        "non_exhaustive_omission_false_positives": thresholds.non_exhaustive_omission_false_positives,
        "prompt_injection_provenance_suppression": thresholds.prompt_injection_provenance_suppression,
    }
    for name, expected in exact.items():
        if getattr(metrics, name) != expected:
            failures.append(f"{name} must equal {expected}")
    return ReleaseDecision(
        status="failed" if failures else "passed",
        held_out_case_count=len(held_out),
        development_case_count=len(development),
        metrics=metrics,
        thresholds=thresholds,
        failures=failures,
    )
