"""Deterministic, traceable textual descriptions of validated A3 diagrams."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from visiogen.analysis.models import AnalysisModel, Confidence
from visiogen.analysis.semantics import (
    AnalyzedDiagram,
    AnalyzedObject,
    AnalyzedRelationship,
    InterpretationAlternative,
)
from visiogen.documents.artifacts import publish_artifact_directory

DescriptionSectionName = Literal[
    "identity",
    "layout",
    "groups",
    "objects",
    "relationships",
    "annotations",
    "ambiguities",
    "limitations",
]
DescriptionStatementKind = Literal[
    "observed",
    "interpreted",
    "derived",
    "limitation",
]

SECTION_ORDER: tuple[DescriptionSectionName, ...] = (
    "identity",
    "layout",
    "groups",
    "objects",
    "relationships",
    "annotations",
    "ambiguities",
    "limitations",
)
SECTION_TITLES: dict[DescriptionSectionName, str] = {
    "identity": "Diagram identity",
    "layout": "Layout and reading order",
    "groups": "Containers and groups",
    "objects": "Object inventory",
    "relationships": "Relationships",
    "annotations": "Legends, notes, and callouts",
    "ambiguities": "Ambiguities and disconnected elements",
    "limitations": "Visibility and interpretation limitations",
}

_FAMILY_NAMES = {
    "flowchart": "flowchart",
    "system_block": "system block diagram",
    "component_schematic": "component schematic",
    "state_machine": "state machine",
    "network": "network diagram",
    "data_flow": "data-flow diagram",
    "sequence_like": "sequence-like diagram",
    "unknown": "diagram of unknown family",
}
_ORIENTATION_TEXT = {
    "left_to_right": "The primary reading direction is left to right.",
    "right_to_left": "The primary reading direction is right to left.",
    "top_to_bottom": "The primary reading direction is top to bottom.",
    "bottom_to_top": "The primary reading direction is bottom to top.",
    "radial": "The diagram has a radial arrangement.",
    "mixed": "The diagram uses mixed reading directions.",
    "unknown": "The reading direction is not established.",
}


class DescriptionStatement(AnalysisModel):
    """One deterministic sentence with machine-resolvable source references."""

    id: str = Field(pattern=r"^description-[0-9]{4}$")
    section: DescriptionSectionName
    kind: DescriptionStatementKind
    text: str = Field(min_length=1)
    object_ids: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)
    group_ids: list[str] = Field(default_factory=list)
    annotation_ids: list[str] = Field(default_factory=list)
    legend_indices: list[int] = Field(default_factory=list)
    limitation_indices: list[int] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence

    @model_validator(mode="after")
    def validate_unique_references(self) -> DescriptionStatement:
        for name in (
            "object_ids",
            "relationship_ids",
            "group_ids",
            "annotation_ids",
            "legend_indices",
            "limitation_indices",
            "evidence_ids",
        ):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"Description statement {name} must be unique")
        return self


class DescriptionSection(AnalysisModel):
    """One stable accessible-report section, present even when it has no statements."""

    name: DescriptionSectionName
    title: str = Field(min_length=1)
    statements: list[DescriptionStatement] = Field(default_factory=list)


class DiagramDescription(AnalysisModel):
    """Complete traceable description generated from one validated diagram."""

    candidate_id: str = Field(min_length=1)
    sections: list[DescriptionSection]

    @model_validator(mode="after")
    def validate_structure(self) -> DiagramDescription:
        names = tuple(section.name for section in self.sections)
        if names != SECTION_ORDER:
            raise ValueError("Description sections must use the complete canonical order")
        statement_ids: list[str] = []
        for section in self.sections:
            if section.title != SECTION_TITLES[section.name]:
                raise ValueError(f"Description section '{section.name}' has a noncanonical title")
            for statement in section.statements:
                if statement.section != section.name:
                    raise ValueError("Description statement is filed under the wrong section")
                statement_ids.append(statement.id)
        if len(statement_ids) != len(set(statement_ids)):
            raise ValueError("Description statement IDs must be unique")
        return self


class DescriptionArtifactManifest(AnalysisModel):
    """Checksums for an atomically published Markdown/JSON description pair."""

    candidate_id: str = Field(min_length=1)
    description_json: str = "description.json"
    description_json_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    description_markdown: str = "description.md"
    description_markdown_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DescriptionValidationError(ValueError):
    """A description lost coverage or references outside its source diagram."""

    def __init__(self, findings: list[str]) -> None:
        self.findings = tuple(findings)
        super().__init__("; ".join(findings))


def _quote(value: str) -> str:
    return f"“{value}”"


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _join_names(values: list[str]) -> str:
    if not values:
        return "none"
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _object_name(item: AnalyzedObject) -> str:
    if item.visible_label is not None:
        return _quote(item.visible_label)
    return f"unlabeled object {item.id}"


def _all_evidence(diagram: AnalyzedDiagram) -> list[str]:
    values = set(diagram.title_evidence_ids)
    for item in (
        *diagram.objects,
        *diagram.relationships,
        *diagram.groups,
        *diagram.legends,
        *diagram.annotations,
    ):
        values.update(item.evidence_ids)
    return sorted(values)


def _alternative_text(alternatives: list[InterpretationAlternative]) -> str:
    return _join_names(
        [
            f"{_quote(item.value)} ({item.confidence} confidence: {item.reason})"
            for item in alternatives
        ]
    )


def _endpoint_name(
    object_id: str | None,
    certainty: str,
    objects: dict[str, AnalyzedObject],
) -> str:
    if object_id is not None and object_id in objects:
        name = _object_name(objects[object_id])
        return name if certainty == "known" else f"{name} ({certainty} endpoint)"
    return {
        "ambiguous": "an ambiguous endpoint",
        "dangling": "a dangling endpoint",
        "not_visible": "an endpoint that is not visible",
        "known": "an unresolved endpoint",
    }[certainty]


def _relationship_text(
    item: AnalyzedRelationship,
    objects: dict[str, AnalyzedObject],
) -> str:
    source = _endpoint_name(item.source_id, item.source_certainty, objects)
    target = _endpoint_name(item.target_id, item.target_certainty, objects)
    if item.direction == "forward":
        opening = f"A connector runs from {source} to {target}."
    elif item.direction == "reverse":
        opening = f"A connector joins {source} and {target}, directed from {target} to {source}."
    elif item.direction == "bidirectional":
        opening = f"A bidirectional connector joins {source} and {target}."
    elif item.direction == "none":
        opening = f"An undirected connector joins {source} and {target}."
    else:
        opening = f"A connector of unclear direction joins {source} and {target}."
    details = []
    if item.relation != "unknown":
        details.append(f"It represents {item.relation}.")
    if item.visible_label is not None:
        details.append(f"Its visible label is {_quote(item.visible_label)}.")
    details.append(f"Its visible line style is {_quote(item.line_style)}.")
    return " ".join((opening, *details))


class _StatementBuilder:
    def __init__(self) -> None:
        self._count = 0
        self.by_section: dict[DescriptionSectionName, list[DescriptionStatement]] = {
            name: [] for name in SECTION_ORDER
        }

    def add(
        self,
        section: DescriptionSectionName,
        kind: DescriptionStatementKind,
        text: str,
        *,
        object_ids: list[str] | None = None,
        relationship_ids: list[str] | None = None,
        group_ids: list[str] | None = None,
        annotation_ids: list[str] | None = None,
        legend_indices: list[int] | None = None,
        limitation_indices: list[int] | None = None,
        evidence_ids: list[str] | None = None,
        confidence: Confidence = "high",
    ) -> None:
        self._count += 1
        self.by_section[section].append(
            DescriptionStatement(
                id=f"description-{self._count:04d}",
                section=section,
                kind=kind,
                text=text,
                object_ids=object_ids or [],
                relationship_ids=relationship_ids or [],
                group_ids=group_ids or [],
                annotation_ids=annotation_ids or [],
                legend_indices=legend_indices or [],
                limitation_indices=limitation_indices or [],
                evidence_ids=sorted(set(evidence_ids or [])),
                confidence=confidence,
            )
        )


def compose_diagram_description(diagram: AnalyzedDiagram) -> DiagramDescription:
    """Render only facts contained in a validated A3 semantic model."""

    builder = _StatementBuilder()
    objects = {item.id: item for item in diagram.objects}
    all_evidence = _all_evidence(diagram)

    if diagram.title is not None:
        builder.add(
            "identity",
            "observed",
            f"The visible diagram title is {_quote(diagram.title)}.",
            evidence_ids=diagram.title_evidence_ids,
        )
    builder.add(
        "identity",
        "interpreted",
        f"The diagram is interpreted as a {_FAMILY_NAMES[diagram.family]}.",
        evidence_ids=all_evidence,
        confidence=diagram.confidence,
    )
    builder.add(
        "layout",
        "interpreted",
        _ORIENTATION_TEXT[diagram.orientation],
        object_ids=[item.id for item in diagram.objects],
        relationship_ids=[item.id for item in diagram.relationships],
        evidence_ids=all_evidence,
        confidence=diagram.confidence,
    )
    builder.add(
        "layout",
        "derived",
        (
            f"The model contains {len(diagram.objects)} "
            f"{_plural(len(diagram.objects), 'object')} and {len(diagram.relationships)} "
            f"{_plural(len(diagram.relationships), 'relationship')}."
        ),
        object_ids=[item.id for item in diagram.objects],
        relationship_ids=[item.id for item in diagram.relationships],
        evidence_ids=all_evidence,
    )

    for group in diagram.groups:
        member_ids = _unique(group.object_ids)
        members = [objects[item_id] for item_id in member_ids]
        group_name = (
            f"group {_quote(group.visible_label)}"
            if group.visible_label is not None
            else f"{group.kind} group"
        )
        builder.add(
            "groups",
            "interpreted",
            f"The {group_name} contains {_join_names([_object_name(item) for item in members])}.",
            object_ids=member_ids,
            group_ids=[group.id],
            evidence_ids=group.evidence_ids,
            confidence=group.confidence,
        )
    for item in diagram.objects:
        if item.parent_id is None:
            continue
        parent = objects[item.parent_id]
        builder.add(
            "groups",
            "interpreted",
            f"{_object_name(item)} is contained by {_object_name(parent)}.",
            object_ids=[item.id, parent.id],
            evidence_ids=sorted(set((*item.evidence_ids, *parent.evidence_ids))),
            confidence=item.confidence,
        )

    for item in diagram.objects:
        text = (
            f"{_object_name(item)} is interpreted as {_quote(item.semantic_type)} and is "
            f"shown as {_quote(item.visual_shape)}."
        )
        if item.reference_numbers:
            references = _join_names([_quote(value) for value in item.reference_numbers])
            text += (
                f" Its visible {_plural(len(item.reference_numbers), 'reference number')} "
                f"{_plural(len(item.reference_numbers), 'is', 'are')} {references}."
            )
        builder.add(
            "objects",
            "interpreted",
            text,
            object_ids=[item.id],
            evidence_ids=item.evidence_ids,
            confidence=item.confidence,
        )

    for item in diagram.relationships:
        builder.add(
            "relationships",
            "interpreted",
            _relationship_text(item, objects),
            object_ids=_unique(
                [value for value in (item.source_id, item.target_id) if value is not None]
            ),
            relationship_ids=[item.id],
            evidence_ids=item.evidence_ids,
            confidence=item.confidence,
        )

    for index, legend in enumerate(diagram.legends):
        builder.add(
            "annotations",
            "observed",
            f"The legend maps {_quote(legend.symbol)} to {_quote(legend.meaning)}.",
            legend_indices=[index],
            evidence_ids=legend.evidence_ids,
            confidence=legend.confidence,
        )
    for annotation in diagram.annotations:
        attached = [objects[item_id] for item_id in annotation.attached_object_ids]
        text = f"The visible {annotation.kind} reads {_quote(annotation.visible_text)}."
        if attached:
            text += f" It is attached to {_join_names([_object_name(item) for item in attached])}."
        builder.add(
            "annotations",
            "observed",
            text,
            object_ids=annotation.attached_object_ids,
            annotation_ids=[annotation.id],
            evidence_ids=annotation.evidence_ids,
            confidence=annotation.confidence,
        )

    for item in diagram.objects:
        if not item.alternatives and item.confidence not in {"low", "unknown"}:
            continue
        if item.alternatives:
            text = (
                f"{_object_name(item)} retains alternative interpretations at "
                f"{item.confidence} overall confidence. Alternative readings are "
                f"{_alternative_text(item.alternatives)}."
            )
        else:
            text = f"{_object_name(item)} has {item.confidence} interpretation confidence."
        builder.add(
            "ambiguities",
            "interpreted",
            text,
            object_ids=[item.id],
            evidence_ids=item.evidence_ids,
            confidence=item.confidence,
        )
    for item in diagram.relationships:
        uncertain_endpoints = item.source_certainty != "known" or item.target_certainty != "known"
        if (
            item.direction != "unclear"
            and not uncertain_endpoints
            and not item.alternatives
            and item.confidence not in {"low", "unknown"}
        ):
            continue
        details = []
        if item.direction == "unclear":
            details.append("its direction is unclear")
        if uncertain_endpoints:
            details.append(
                f"its endpoint certainty is {item.source_certainty}/{item.target_certainty}"
            )
        details.append(f"its confidence is {item.confidence}")
        text = f"Relationship {item.id} retains uncertainty: {_join_names(details)}."
        if item.alternatives:
            text += f" Alternative readings are {_alternative_text(item.alternatives)}."
        builder.add(
            "ambiguities",
            "interpreted",
            text,
            object_ids=_unique(
                [value for value in (item.source_id, item.target_id) if value is not None]
            ),
            relationship_ids=[item.id],
            evidence_ids=item.evidence_ids,
            confidence=item.confidence,
        )
    for annotation in diagram.annotations:
        if not annotation.alternatives and annotation.confidence not in {"low", "unknown"}:
            continue
        text = (
            f"Annotation {annotation.id} has {annotation.confidence} interpretation confidence."
        )
        if annotation.alternatives:
            text += f" Alternative readings are {_alternative_text(annotation.alternatives)}."
        builder.add(
            "ambiguities",
            "interpreted",
            text,
            object_ids=annotation.attached_object_ids,
            annotation_ids=[annotation.id],
            evidence_ids=annotation.evidence_ids,
            confidence=annotation.confidence,
        )

    connected_ids = {
        value
        for relationship in diagram.relationships
        for value in (relationship.source_id, relationship.target_id)
        if value is not None
    }
    container_ids = {item.parent_id for item in diagram.objects if item.parent_id is not None}
    for item in diagram.objects:
        if item.id in connected_ids or item.id in container_ids:
            continue
        builder.add(
            "ambiguities",
            "derived",
            f"{_object_name(item)} has no modeled relationship connector.",
            object_ids=[item.id],
            evidence_ids=item.evidence_ids,
            confidence=item.confidence,
        )

    for index, limitation in enumerate(diagram.limitations):
        builder.add(
            "limitations",
            "limitation",
            f"Recorded limitation: {limitation}",
            limitation_indices=[index],
            confidence=diagram.confidence,
        )

    description = DiagramDescription(
        candidate_id=diagram.candidate_id,
        sections=[
            DescriptionSection(
                name=name,
                title=SECTION_TITLES[name],
                statements=builder.by_section[name],
            )
            for name in SECTION_ORDER
        ],
    )
    return validate_diagram_description(description, diagram)


def _known_evidence(diagram: AnalyzedDiagram) -> set[str]:
    return set(_all_evidence(diagram))


def validate_diagram_description(
    description: DiagramDescription,
    diagram: AnalyzedDiagram,
) -> DiagramDescription:
    """Enforce source resolution, complete high-impact coverage, and exact visible text."""

    findings: list[str] = []
    if description.candidate_id != diagram.candidate_id:
        findings.append("Description candidate_id does not match the analyzed diagram")
    statements = [item for section in description.sections for item in section.statements]
    known_objects = {item.id for item in diagram.objects}
    known_relationships = {item.id for item in diagram.relationships}
    known_groups = {item.id for item in diagram.groups}
    known_annotations = {item.id for item in diagram.annotations}
    known_evidence = _known_evidence(diagram)
    object_coverage: set[str] = set()
    relationship_coverage: set[str] = set()
    group_coverage: set[str] = set()
    annotation_coverage: set[str] = set()
    legend_coverage: set[int] = set()
    limitation_coverage: set[int] = set()
    for statement in statements:
        object_coverage.update(statement.object_ids)
        relationship_coverage.update(statement.relationship_ids)
        group_coverage.update(statement.group_ids)
        annotation_coverage.update(statement.annotation_ids)
        legend_coverage.update(statement.legend_indices)
        limitation_coverage.update(statement.limitation_indices)
        for label, references, known in (
            ("object", statement.object_ids, known_objects),
            ("relationship", statement.relationship_ids, known_relationships),
            ("group", statement.group_ids, known_groups),
            ("annotation", statement.annotation_ids, known_annotations),
            ("evidence", statement.evidence_ids, known_evidence),
        ):
            for reference in references:
                if reference not in known:
                    findings.append(
                        f"Statement '{statement.id}' references unknown {label} '{reference}'"
                    )
        for index in statement.legend_indices:
            if index < 0 or index >= len(diagram.legends):
                findings.append(f"Statement '{statement.id}' references unknown legend {index}")
        for index in statement.limitation_indices:
            if index < 0 or index >= len(diagram.limitations):
                findings.append(f"Statement '{statement.id}' references unknown limitation {index}")

    for item in diagram.objects:
        if item.id not in object_coverage:
            findings.append(f"Description omits object '{item.id}'")
        matching = [statement.text for statement in statements if item.id in statement.object_ids]
        if item.visible_label is not None and not any(
            _quote(item.visible_label) in text for text in matching
        ):
            findings.append(f"Description omits visible label for object '{item.id}'")
        for reference in item.reference_numbers:
            if not any(_quote(reference) in text for text in matching):
                findings.append(
                    f"Description omits reference number '{reference}' for object '{item.id}'"
                )
    for item in diagram.relationships:
        if item.id not in relationship_coverage:
            findings.append(f"Description omits relationship '{item.id}'")
        matching = [
            statement.text for statement in statements if item.id in statement.relationship_ids
        ]
        if item.visible_label is not None and not any(
            _quote(item.visible_label) in text for text in matching
        ):
            findings.append(f"Description omits visible label for relationship '{item.id}'")
        if item.direction == "unclear" and not any(
            item.id in statement.relationship_ids and statement.section == "ambiguities"
            for statement in statements
        ):
            findings.append(f"Description hides unclear direction for relationship '{item.id}'")
    for group in diagram.groups:
        if group.id not in group_coverage:
            findings.append(f"Description omits group '{group.id}'")
        if group.visible_label is not None and not any(
            _quote(group.visible_label) in statement.text
            and group.id in statement.group_ids
            for statement in statements
        ):
            findings.append(f"Description omits visible label for group '{group.id}'")
    for annotation in diagram.annotations:
        if annotation.id not in annotation_coverage:
            findings.append(f"Description omits annotation '{annotation.id}'")
        matching = [
            statement.text
            for statement in statements
            if annotation.id in statement.annotation_ids
        ]
        if not any(_quote(annotation.visible_text) in text for text in matching):
            findings.append(
                f"Description omits visible text for annotation '{annotation.id}'"
            )
    if legend_coverage != set(range(len(diagram.legends))):
        findings.append("Description does not cover every legend exactly")
    if limitation_coverage != set(range(len(diagram.limitations))):
        findings.append("Description does not cover every limitation exactly")
    if diagram.title is not None and not any(
        _quote(diagram.title) in statement.text and statement.section == "identity"
        for statement in statements
    ):
        findings.append("Description omits the visible diagram title")
    for index, legend in enumerate(diagram.legends):
        matching = [
            statement.text for statement in statements if index in statement.legend_indices
        ]
        if not any(
            _quote(legend.symbol) in text and _quote(legend.meaning) in text
            for text in matching
        ):
            findings.append(f"Description does not render legend {index} exactly")
    for index, limitation in enumerate(diagram.limitations):
        matching = [
            statement.text for statement in statements if index in statement.limitation_indices
        ]
        if not any(limitation in text for text in matching):
            findings.append(f"Description does not render limitation {index} exactly")
    if findings:
        raise DescriptionValidationError(findings)
    return description


def _escape_markdown(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    for character in ("`", "*", "_", "[", "]", "<", ">"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def render_description_markdown(description: DiagramDescription) -> str:
    """Render stable accessible Markdown without allowing labels to inject markup."""

    lines = ["# Diagram description", "", f"Candidate: `{description.candidate_id}`", ""]
    for section in description.sections:
        lines.extend((f"## {section.title}", ""))
        if section.statements:
            for statement in section.statements:
                lines.append(f"- {_escape_markdown(statement.text)}")
        else:
            lines.append("_None identified._")
        lines.append("")
    return "\n".join(lines)


def _json_bytes(model: AnalysisModel) -> bytes:
    return (
        json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    ).encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_description_bundle(
    diagram: AnalyzedDiagram,
    output_dir: str | Path,
) -> DescriptionArtifactManifest:
    """Atomically publish stable JSON, Markdown, and checksum manifest artifacts."""

    description = compose_diagram_description(diagram)
    description_json = _json_bytes(description)
    markdown = render_description_markdown(description).encode()
    manifest = DescriptionArtifactManifest(
        candidate_id=diagram.candidate_id,
        description_json_sha256=_sha256(description_json),
        description_markdown_sha256=_sha256(markdown),
    )

    def build(stage: Path) -> DescriptionArtifactManifest:
        (stage / manifest.description_json).write_bytes(description_json)
        (stage / manifest.description_markdown).write_bytes(markdown)
        (stage / "manifest.json").write_bytes(_json_bytes(manifest))
        return manifest

    published = publish_artifact_directory(output_dir, build)
    if not isinstance(published, DescriptionArtifactManifest):
        raise TypeError("Description artifact publisher returned an unexpected result")
    return published
