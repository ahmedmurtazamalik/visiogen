"""Frozen corpus and baseline contracts for Generation v2 quality work."""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DiagramFamily = Literal[
    "branching_flowchart",
    "system_architecture",
    "contained_schematic",
    "dense_process",
    "nested_architecture",
    "patent_schematic",
    "long_label",
    "reciprocal_self_loop",
    "professional_style",
    "document_reconstruction",
]
InputMode = Literal["text", "professional_spec", "analysis_import"]
EvidenceState = Literal["measured", "unavailable", "not_run"]

REQUIRED_FAMILIES = frozenset(
    {
        "branching_flowchart",
        "system_architecture",
        "contained_schematic",
        "dense_process",
        "nested_architecture",
        "patent_schematic",
        "long_label",
        "reciprocal_self_loop",
        "professional_style",
        "document_reconstruction",
    }
)
REQUIRED_COVERAGE_TAGS = frozenset(
    {
        "branching",
        "containment",
        "crossing_pressure",
        "long_labels",
        "nested_containers",
        "reference_callouts",
        "reciprocal_edges",
        "self_loop",
        "professional_constraints",
        "analysis_import",
    }
)


class GenerationEvaluationModel(BaseModel):
    """Strict base for immutable generation-evaluation artifacts."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ExpectedRelationship(GenerationEvaluationModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    direction: Literal["forward", "reverse", "bidirectional", "undirected"]
    label: str | None = None


class GenerationCorpusCase(GenerationEvaluationModel):
    """One source-independent generation-quality case."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    family: DiagramFamily
    input_mode: InputMode
    source: str | dict[str, object]
    expected_objects: list[str] = Field(min_length=1)
    expected_relationships: list[ExpectedRelationship] = Field(default_factory=list)
    required_conditions: list[str] = Field(min_length=1)
    forbidden_conditions: list[str] = Field(min_length=1)
    coverage_tags: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case(self) -> GenerationCorpusCase:
        if len(self.expected_objects) != len(set(self.expected_objects)):
            raise ValueError("Expected object IDs must be unique within a case")
        known = set(self.expected_objects)
        for relationship in self.expected_relationships:
            if relationship.source not in known or relationship.target not in known:
                raise ValueError("Expected relationships must reference expected objects")
        if len(self.coverage_tags) != len(set(self.coverage_tags)):
            raise ValueError("Coverage tags must be unique within a case")
        if self.input_mode == "text" and not isinstance(self.source, str):
            raise ValueError("Text cases require a string source")
        if self.input_mode != "text" and not isinstance(self.source, dict):
            raise ValueError("Structured cases require an object source")
        return self


class GenerationThresholds(GenerationEvaluationModel):
    """Frozen initial Generation v2 release thresholds."""

    shape_or_label_overlaps_maximum: int = Field(default=0, ge=0)
    arrowheads_inside_unrelated_shapes_maximum: int = Field(default=0, ge=0)
    connectors_crossing_unrelated_labels_maximum: int = Field(default=0, ge=0)
    callout_leaders_crossing_unrelated_labels_maximum: int = Field(default=0, ge=0)
    required_direction_accuracy_minimum: float = Field(default=1.0, ge=0, le=1)
    required_containment_accuracy_minimum: float = Field(default=1.0, ge=0, le=1)
    unresolved_high_severity_findings_maximum: int = Field(default=0, ge=0)
    v2_human_preference_minimum: float = Field(default=0.8, ge=0, le=1)
    supported_run_completion_minimum: float = Field(default=0.9, ge=0, le=1)


class GenerationCorpus(GenerationEvaluationModel):
    version: int = Field(ge=1)
    frozen: bool
    cases: list[GenerationCorpusCase] = Field(min_length=1)
    thresholds: GenerationThresholds = Field(default_factory=GenerationThresholds)


class CorpusValidation(GenerationEvaluationModel):
    valid: bool
    case_count: int
    families: list[str]
    coverage_tags: list[str]
    failures: list[str]


def validate_generation_corpus(corpus: GenerationCorpus) -> CorpusValidation:
    """Enforce the frozen G0 coverage and identity contract."""

    failures: list[str] = []
    ids = [case.id for case in corpus.cases]
    duplicate_ids = sorted(item for item, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        failures.append("corpus case IDs must be unique: " + ", ".join(duplicate_ids))
    families = {case.family for case in corpus.cases}
    missing_families = REQUIRED_FAMILIES - families
    if missing_families:
        failures.append("corpus missing families: " + ", ".join(sorted(missing_families)))
    tags = {tag for case in corpus.cases for tag in case.coverage_tags}
    missing_tags = REQUIRED_COVERAGE_TAGS - tags
    if missing_tags:
        failures.append("corpus missing coverage: " + ", ".join(sorted(missing_tags)))
    if not corpus.frozen:
        failures.append("corpus must declare frozen=true")
    return CorpusValidation(
        valid=not failures,
        case_count=len(corpus.cases),
        families=sorted(families),
        coverage_tags=sorted(tags),
        failures=failures,
    )


class BaselineCaseResult(GenerationEvaluationModel):
    case_id: str = Field(min_length=1)
    evidence_state: EvidenceState
    reason: str = Field(min_length=1)
    generation_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    preview_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    vsdx_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    native_visio_status: str | None = None
    human_review_status: str | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> BaselineCaseResult:
        hashes = (
            self.generation_manifest_sha256,
            self.preview_sha256,
            self.vsdx_sha256,
        )
        if self.evidence_state == "measured" and not all(hashes):
            raise ValueError("Measured baseline cases require manifest, preview, and VSDX hashes")
        if self.evidence_state != "measured" and any(hashes):
            raise ValueError("Unavailable or unrun cases cannot claim artifact hashes")
        return self


class BaselineReport(GenerationEvaluationModel):
    """Checksum-bound Generation v1 comparison baseline."""

    report_version: int = Field(default=1, ge=1)
    status: Literal["complete", "incomplete"]
    source_revision: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    corpus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_test_count: int = Field(ge=0)
    generation_tests_passed: bool
    current_limitations: list[str] = Field(min_length=1)
    cases: list[BaselineCaseResult] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status(self) -> BaselineReport:
        states = {case.evidence_state for case in self.cases}
        expected = "complete" if states == {"measured"} else "incomplete"
        if self.status != expected:
            raise ValueError(f"Baseline status must be {expected} for its evidence states")
        return self


def validate_baseline_report(
    corpus: GenerationCorpus, report: BaselineReport
) -> list[str]:
    """Bind one baseline report to exactly one frozen corpus."""

    failures: list[str] = []
    expected_ids = [case.id for case in corpus.cases]
    actual_ids = [case.case_id for case in report.cases]
    if len(actual_ids) != len(set(actual_ids)):
        failures.append("baseline case IDs must be unique")
    missing = sorted(set(expected_ids) - set(actual_ids))
    unknown = sorted(set(actual_ids) - set(expected_ids))
    if missing:
        failures.append("baseline missing cases: " + ", ".join(missing))
    if unknown:
        failures.append("baseline references unknown cases: " + ", ".join(unknown))
    return failures


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
