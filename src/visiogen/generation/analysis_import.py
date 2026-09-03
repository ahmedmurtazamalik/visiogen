"""Checksum-bound analysis-bundle import without analysis-package dependencies."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from visiogen.generation.specification import (
    DiagramSpecification,
    ReviewItem,
    ReviewItemKind,
    SpecificationGroup,
    SpecificationObject,
    SpecificationRelationship,
    SpecificationSource,
    VisualRequirement,
)
from visiogen.models import NodeType

Confidence = Literal["high", "medium", "low", "unknown"]


class AnalysisImportError(ValueError):
    """Raised when a bundle is unsafe, inconsistent, or cannot be projected."""


class ImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ArtifactRecord(ImportModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)


class AnalysisBundleManifest(ImportModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_byte_size: int = Field(gt=0)
    document_kind: Literal["pdf", "docx"]
    application_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    started_at_utc: str = Field(min_length=1)
    completed_at_utc: str = Field(min_length=1)
    total_elapsed_ms: float = Field(ge=0)
    total_model_calls: int = Field(ge=0)
    classification_elapsed_ms: float | None = Field(default=None, ge=0)
    source_revision: str | None = None
    source_worktree_clean: bool | None = None
    tools: dict[str, str]
    schema_sha256: dict[str, str]
    artifacts: list[ArtifactRecord]
    warnings: list[str]
    partial_failures: list[str]

    @model_validator(mode="after")
    def validate_artifact_paths(self) -> AnalysisBundleManifest:
        paths = [item.path for item in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("analysis manifest artifact paths must be unique")
        return self


class Box(ImportModel):
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)


class Point(ImportModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Alternative(ImportModel):
    value: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    confidence: Confidence


class ImportedObject(ImportModel):
    id: str = Field(pattern=r"^object-[0-9]{4}$")
    visible_label: str | None = None
    normalized_label: str | None = None
    semantic_type: str = Field(min_length=1)
    visual_shape: str = Field(min_length=1)
    reference_numbers: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    bbox: Box
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    alternatives: list[Alternative] = Field(default_factory=list)


class ImportedRelationship(ImportModel):
    id: str = Field(pattern=r"^relationship-[0-9]{4}$")
    source_id: str | None = None
    target_id: str | None = None
    source_certainty: Literal["known", "ambiguous", "dangling", "not_visible"]
    target_certainty: Literal["known", "ambiguous", "dangling", "not_visible"]
    direction: Literal["forward", "reverse", "bidirectional", "none", "unclear"]
    relation: Literal[
        "flow", "data", "control", "power", "communication", "mechanical",
        "association", "unknown",
    ]
    visible_label: str | None = None
    normalized_label: str | None = None
    path: list[Point] = Field(default_factory=list)
    line_style: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    alternatives: list[Alternative] = Field(default_factory=list)


class ImportedGroup(ImportModel):
    id: str = Field(pattern=r"^group-[0-9]{4}$")
    kind: str = Field(min_length=1)
    visible_label: str | None = None
    object_ids: list[str] = Field(default_factory=list)
    bbox: Box
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence


class ImportedLegend(ImportModel):
    symbol: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence


class ImportedAnnotation(ImportModel):
    id: str = Field(pattern=r"^annotation-[0-9]{4}$")
    kind: Literal["note", "callout"]
    visible_text: str = Field(min_length=1)
    attached_object_ids: list[str] = Field(default_factory=list)
    bbox: Box
    evidence_ids: list[str] = Field(min_length=1)
    confidence: Confidence
    alternatives: list[Alternative] = Field(default_factory=list)


class ImportedDiagram(ImportModel):
    candidate_id: str = Field(pattern=r"^candidate-[0-9]{4}$")
    title: str | None = None
    title_evidence_ids: list[str] = Field(default_factory=list)
    family: Literal[
        "flowchart", "system_block", "component_schematic", "state_machine",
        "network", "data_flow", "sequence_like", "unknown",
    ]
    orientation: Literal[
        "left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top",
        "radial", "mixed", "unknown",
    ]
    objects: list[ImportedObject] = Field(min_length=1)
    relationships: list[ImportedRelationship]
    groups: list[ImportedGroup] = Field(default_factory=list)
    legends: list[ImportedLegend] = Field(default_factory=list)
    annotations: list[ImportedAnnotation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: Confidence

    @model_validator(mode="after")
    def validate_references(self) -> ImportedDiagram:
        object_ids = {item.id for item in self.objects}
        for item in self.objects:
            if item.parent_id is not None and item.parent_id not in object_ids:
                raise ValueError(f"object '{item.id}' references unknown parent")
        for group in self.groups:
            if set(group.object_ids) - object_ids:
                raise ValueError(f"group '{group.id}' references unknown objects")
        for annotation in self.annotations:
            if set(annotation.attached_object_ids) - object_ids:
                raise ValueError(f"annotation '{annotation.id}' references unknown objects")
        return self


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_artifact(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
        raise AnalysisImportError(f"unsafe analysis artifact path: {relative}")
    path = root.joinpath(*pure.parts)
    if path.is_symlink() or not path.is_file():
        raise AnalysisImportError(f"analysis artifact is missing or unsafe: {relative}")
    return path


def _verified_artifact(root: Path, record: ArtifactRecord) -> Path:
    path = _safe_artifact(root, record.path)
    if path.stat().st_size != record.byte_size or _sha256(path) != record.sha256:
        raise AnalysisImportError(
            f"analysis artifact does not match manifest checksum: {record.path}"
        )
    return path


def _evidence_ids(path: Path, candidate_id: str) -> set[str]:
    try:
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict) or value.get("candidate_id") != candidate_id:
            raise ValueError("candidate ID does not match")
        evidence = value.get("evidence")
        if not isinstance(evidence, list):
            raise ValueError("evidence must be a list")
        identifiers = [item.get("id") for item in evidence if isinstance(item, dict)]
        if len(identifiers) != len(evidence) or any(
            not isinstance(item, str) or re.fullmatch(r"evidence-[0-9]{4}", item) is None
            for item in identifiers
        ):
            raise ValueError("evidence entries require valid IDs")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("evidence IDs must be unique")
        return set(identifiers)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise AnalysisImportError(f"invalid validated observations: {error}") from error


def _identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not normalized or not normalized[0].isalpha():
        normalized = f"item_{normalized}"
    return normalized


def _review(
    identifier: str,
    description: str,
    evidence: list[str],
    *,
    kind: ReviewItemKind = "ambiguity",
) -> ReviewItem:
    return ReviewItem(
        id=_identifier(identifier),
        kind=kind,
        description=description,
        permitted=True,
        evidence_refs=evidence,
    )


_NODE_TYPES = set(NodeType.__args__)
_NODE_ALIASES = {
    "system": "subsystem",
    "container": "subsystem",
    "block": "component",
    "storage": "data_store",
    "user": "external_system",
}


def project_analysis_diagram(
    diagram: ImportedDiagram,
    source: SpecificationSource,
) -> DiagramSpecification:
    """Project supported facts and retain every uncertain item for human review."""

    review_items: list[ReviewItem] = []
    object_ids = {item.id: _identifier(item.id) for item in diagram.objects}
    objects: list[SpecificationObject] = []
    for item in diagram.objects:
        mapped_type = _NODE_ALIASES.get(item.semantic_type, item.semantic_type)
        if mapped_type not in _NODE_TYPES:
            review_items.append(
                _review(
                    f"{item.id}_unsupported_type",
                    f"Object '{item.id}' has unsupported semantic type "
                    f"'{item.semantic_type}'; projected as component.",
                    item.evidence_ids,
                    kind="unsupported",
                )
            )
            mapped_type = "component"
        if item.confidence != "high" or item.alternatives:
            alternatives = "; ".join(
                f"{value.value} ({value.confidence}: {value.reason})"
                for value in item.alternatives
            ) or "none recorded"
            review_items.append(
                _review(
                    f"{item.id}_uncertainty",
                    f"Object '{item.id}' confidence is {item.confidence}; alternatives: "
                    f"{alternatives}.",
                    item.evidence_ids,
                )
            )
        label = item.visible_label or item.normalized_label
        if label is None:
            label = item.id
            review_items.append(
                _review(
                    f"{item.id}_missing_label",
                    f"Object '{item.id}' has no visible label; placeholder retained.",
                    item.evidence_ids,
                    kind="unknown",
                )
            )
        objects.append(
            SpecificationObject(
                id=object_ids[item.id],
                label=label,
                type=mapped_type,
                required=item.confidence == "high" and not item.alternatives,
                parent_id=object_ids.get(item.parent_id),
                reference_number=(
                    ", ".join(item.reference_numbers) if item.reference_numbers else None
                ),
                notes=f"Observed as {item.visual_shape}.",
                evidence_refs=item.evidence_ids,
            )
        )

    relationships: list[SpecificationRelationship] = []
    for item in diagram.relationships:
        fully_known = (
            item.source_certainty == "known"
            and item.target_certainty == "known"
            and item.source_id in object_ids
            and item.target_id in object_ids
            and item.direction != "unclear"
            and item.relation != "unknown"
        )
        uncertain = item.confidence != "high" or bool(item.alternatives)
        if not fully_known or uncertain:
            review_items.append(
                _review(
                    f"{item.id}_uncertainty",
                    f"Relationship '{item.id}' requires review: source="
                    f"{item.source_id or item.source_certainty}, target="
                    f"{item.target_id or item.target_certainty}, direction={item.direction}, "
                    f"relation={item.relation}, confidence={item.confidence}.",
                    item.evidence_ids,
                )
            )
            continue
        relationships.append(
            SpecificationRelationship(
                id=_identifier(item.id),
                source=object_ids[item.source_id],  # type: ignore[index]
                target=object_ids[item.target_id],  # type: ignore[index]
                relation=item.relation,  # type: ignore[arg-type]
                direction=item.direction,  # type: ignore[arg-type]
                label=item.visible_label,
                required=True,
                evidence_refs=item.evidence_ids,
            )
        )

    groups = [
        SpecificationGroup(
            id=_identifier(item.id),
            kind=item.kind,
            label=item.visible_label,
            object_ids=[object_ids[value] for value in item.object_ids],
            confidence=item.confidence,
            evidence_refs=item.evidence_ids,
        )
        for item in diagram.groups
    ]
    for group in diagram.groups:
        if group.confidence != "high":
            review_items.append(
                _review(
                    f"{group.id}_uncertainty",
                    f"Group '{group.id}' confidence is {group.confidence}.",
                    group.evidence_ids,
                )
            )
    for annotation in diagram.annotations:
        review_items.append(
            _review(
                f"{annotation.id}_{annotation.kind}",
                f"Preserve {annotation.kind}: {annotation.visible_text}",
                annotation.evidence_ids,
                kind="annotation",
            )
        )
    for index, legend in enumerate(diagram.legends, start=1):
        review_items.append(
            _review(
                f"legend_{index}",
                f"Preserve legend mapping '{legend.symbol}' = '{legend.meaning}'.",
                legend.evidence_ids,
                kind="legend",
            )
        )
    for index, limitation in enumerate(diagram.limitations, start=1):
        review_items.append(
            _review(f"limitation_{index}", limitation, [], kind="limitation")
        )

    family_map = {
        "flowchart": "flowchart",
        "state_machine": "flowchart",
        "component_schematic": "component_schematic",
    }
    diagram_type = family_map.get(diagram.family, "system_block")
    notation = {
        "flowchart": "flowchart",
        "component_schematic": "component",
    }.get(diagram_type, "system")
    orientation = diagram.orientation
    if orientation not in {"left_to_right", "top_to_bottom"}:
        mapped = "top_to_bottom" if orientation == "bottom_to_top" else "left_to_right"
        review_items.append(
            _review(
                "orientation_projection",
                f"Observed orientation '{orientation}' is unsupported and was projected as "
                f"'{mapped}'; reviewer confirmation is required.",
                diagram.title_evidence_ids,
                kind="unsupported",
            )
        )
        orientation = mapped
    if diagram.family == "unknown":
        review_items.append(
            _review(
                "diagram_family_unknown",
                "Diagram family is unknown; system notation is a provisional projection.",
                diagram.title_evidence_ids,
                kind="unknown",
            )
        )

    return DiagramSpecification(
        title=diagram.title or f"Imported {diagram.candidate_id}",
        purpose="Reconstruct the visible meaning of the analyzed diagram as an editable draft.",
        audience="Reviewer of the imported document diagram",
        diagram_type=diagram_type,  # type: ignore[arg-type]
        notation=notation,  # type: ignore[arg-type]
        orientation=orientation,  # type: ignore[arg-type]
        primary_flow="Preserve the analyzed relationship directions and visible grouping.",
        source=source,
        objects=objects,
        relationships=relationships,
        groups=groups,
        review_items=review_items,
        visual_requirements=[
            VisualRequirement(
                id="preserve_visible_labels",
                description="Preserve exact visible labels and reference numerals.",
            )
        ],
        forbidden_conditions=[
            "Do not convert review items into asserted objects or relationships.",
            "Do not invent content absent from the analyzed visual evidence.",
        ],
    )


def import_analysis_bundle(
    bundle_path: str | Path,
    *,
    candidate_id: str | None = None,
) -> DiagramSpecification:
    """Verify one analysis bundle and project one explicit completed candidate."""

    root = Path(bundle_path)
    if root.is_symlink() or not root.is_dir():
        raise AnalysisImportError("analysis bundle must be a non-symlink directory")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise AnalysisImportError("analysis bundle manifest.json was not found")
    try:
        manifest = AnalysisBundleManifest.model_validate_json(manifest_path.read_bytes())
    except (OSError, ValidationError) as error:
        raise AnalysisImportError(f"invalid analysis manifest: {error}") from error

    diagram_records = [
        item
        for item in manifest.artifacts
        if PurePosixPath(item.path).name == "24-analyzed-diagram.json"
    ]
    if candidate_id is not None:
        expected_path = f"{candidate_id}/24-analyzed-diagram.json"
        diagram_records = [item for item in diagram_records if item.path == expected_path]
        if not diagram_records:
            raise AnalysisImportError(
                f"completed candidate '{candidate_id}' was not found in the analysis bundle"
            )
    elif len(diagram_records) != 1:
        raise AnalysisImportError(
            "analysis bundle must contain exactly one completed candidate; "
            "select one with --analysis-candidate"
        )
    record = diagram_records[0]
    diagram_path = _verified_artifact(root, record)
    try:
        diagram = ImportedDiagram.model_validate_json(diagram_path.read_bytes())
    except (OSError, ValidationError) as error:
        raise AnalysisImportError(f"invalid analyzed diagram: {error}") from error
    expected_candidate = PurePosixPath(record.path).parts[0]
    if diagram.candidate_id != expected_candidate:
        raise AnalysisImportError("analyzed diagram candidate ID does not match its path")

    observation_path = f"{diagram.candidate_id}/14-validated-observations.json"
    observation_records = [
        item for item in manifest.artifacts if item.path == observation_path
    ]
    if len(observation_records) != 1:
        raise AnalysisImportError(
            f"analysis manifest must contain exactly one {observation_path} artifact"
        )
    known_evidence = _evidence_ids(
        _verified_artifact(root, observation_records[0]), diagram.candidate_id
    )
    cited_evidence = set(diagram.title_evidence_ids)
    for item in [
        *diagram.objects,
        *diagram.relationships,
        *diagram.groups,
        *diagram.legends,
        *diagram.annotations,
    ]:
        cited_evidence.update(item.evidence_ids)
    missing_evidence = sorted(cited_evidence - known_evidence)
    if missing_evidence:
        raise AnalysisImportError(
            "analyzed diagram references unknown evidence: "
            + ", ".join(missing_evidence)
        )

    source = SpecificationSource(
        kind="analysis_bundle",
        document_kind=manifest.document_kind,
        source_name=manifest.source_name,
        source_sha256=manifest.source_sha256,
        candidate_id=diagram.candidate_id,
        provider=manifest.provider,
        model=manifest.model,
        manifest_sha256=_sha256(manifest_path),
        analyzed_diagram_sha256=record.sha256,
    )
    return project_analysis_diagram(diagram, source)


def write_specification(path: str | Path, specification: DiagramSpecification) -> Path:
    """Publish a stable human-reviewable JSON specification without overwriting."""

    output = Path(path)
    if output.suffix.lower() != ".json":
        raise AnalysisImportError("specification output must use .json")
    if output.is_symlink() or output.exists():
        raise AnalysisImportError("specification output path must not already exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        specification.model_dump(mode="json"), indent=2, sort_keys=True
    ) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent, prefix=f".{output.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
        descriptor = -1
        temporary.chmod(0o600)
        try:
            os.link(temporary, output)
        except FileExistsError as error:
            raise AnalysisImportError(
                "specification output path must not already exist"
            ) from error
        temporary.unlink()
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    return output
