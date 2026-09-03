"""Versioned professional diagram specification and deterministic validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from visiogen.design import VisualImportance
from visiogen.models import (
    DiagramType,
    DirectionType,
    NodeType,
    Orientation,
    RelationType,
)

Confidence = Literal["high", "medium", "low", "unknown"]

ConstraintStrength = Literal["hard", "preference"]
ConstraintKind = Literal["ordering", "adjacency", "alignment", "separation"]
Notation = Literal["flowchart", "system", "component", "patent", "custom"]
ReviewItemKind = Literal[
    "ambiguity", "unknown", "unsupported", "annotation", "legend", "limitation"
]


class SpecificationError(ValueError):
    """Raised when a specification file cannot be read or validated."""


class SpecificationModel(BaseModel):
    """Strict base for user-authored and model-produced specification data."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SpecificationObject(SpecificationModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    type: NodeType
    required: bool = True
    parent_id: str | None = None
    reference_number: str | None = None
    importance: VisualImportance = "secondary"
    notes: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class SpecificationRelationship(SpecificationModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source: str
    target: str
    relation: RelationType = "flow"
    direction: DirectionType = "forward"
    label: str | None = None
    required: bool = True
    evidence_refs: list[str] = Field(default_factory=list)


class SpecificationGroup(SpecificationModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: str = Field(min_length=1)
    label: str | None = None
    object_ids: list[str] = Field(default_factory=list)
    confidence: Confidence
    evidence_refs: list[str] = Field(min_length=1)


class SpecificationSource(SpecificationModel):
    kind: Literal["analysis_bundle"]
    boundary_version: Literal[1] = 1
    document_kind: Literal["pdf", "docx"]
    source_name: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analyzed_diagram_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CompositionConstraint(SpecificationModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: ConstraintKind
    object_ids: list[str] = Field(min_length=2)
    strength: ConstraintStrength = "hard"
    axis: Literal["horizontal", "vertical"] | None = None
    minimum_distance: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_kind_fields(self) -> CompositionConstraint:
        if len(self.object_ids) != len(set(self.object_ids)):
            raise ValueError("constraint object_ids must be unique")
        if self.kind == "alignment" and self.axis is None:
            raise ValueError("alignment constraints require axis")
        if self.kind != "alignment" and self.axis is not None:
            raise ValueError("axis is only valid for alignment constraints")
        if self.kind == "separation" and self.minimum_distance is None:
            raise ValueError("separation constraints require minimum_distance")
        if self.kind != "separation" and self.minimum_distance is not None:
            raise ValueError("minimum_distance is only valid for separation constraints")
        return self


class DraftingPreferences(SpecificationModel):
    shape_family: str | None = None
    color_direction: str | None = None
    typography: str | None = None
    connector_style: Literal["orthogonal", "straight", "curved", "model_choice"] = (
        "model_choice"
    )


class ReviewItem(SpecificationModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: ReviewItemKind
    description: str = Field(min_length=1)
    permitted: bool = True
    evidence_refs: list[str] = Field(default_factory=list)


class VisualRequirement(SpecificationModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)
    metric: str | None = None
    operator: Literal["eq", "lte", "gte"] | None = None
    value: float | None = None

    @model_validator(mode="after")
    def validate_measurement(self) -> VisualRequirement:
        supplied = (self.metric is not None, self.operator is not None, self.value is not None)
        if any(supplied) and not all(supplied):
            raise ValueError("metric, operator, and value must be supplied together")
        return self


class DiagramSpecification(SpecificationModel):
    """Source-faithful semantic and drafting contract before visual construction."""

    version: Literal[1] = 1
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    diagram_type: DiagramType
    notation: Notation
    orientation: Orientation
    primary_flow: str = Field(min_length=1)
    source: SpecificationSource | None = None
    objects: list[SpecificationObject] = Field(min_length=1)
    relationships: list[SpecificationRelationship] = Field(default_factory=list)
    groups: list[SpecificationGroup] = Field(default_factory=list)
    constraints: list[CompositionConstraint] = Field(default_factory=list)
    drafting: DraftingPreferences = Field(default_factory=DraftingPreferences)
    review_items: list[ReviewItem] = Field(default_factory=list)
    visual_requirements: list[VisualRequirement] = Field(min_length=1)
    forbidden_conditions: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references_and_constraints(self) -> DiagramSpecification:
        object_ids = [item.id for item in self.objects]
        relationship_ids = [item.id for item in self.relationships]
        group_ids = [item.id for item in self.groups]
        constraint_ids = [item.id for item in self.constraints]
        review_ids = [item.id for item in self.review_items]
        visual_ids = [item.id for item in self.visual_requirements]
        for label, values in (
            ("object", object_ids),
            ("relationship", relationship_ids),
            ("group", group_ids),
            ("constraint", constraint_ids),
            ("review item", review_ids),
            ("visual requirement", visual_ids),
        ):
            duplicates = sorted({value for value in values if values.count(value) > 1})
            if duplicates:
                raise ValueError(f"duplicate {label} IDs: {', '.join(duplicates)}")

        known = set(object_ids)
        for item in self.objects:
            if item.parent_id is not None and item.parent_id not in known:
                raise ValueError(
                    f"object '{item.id}' references unknown parent '{item.parent_id}'"
                )
            if item.parent_id == item.id:
                raise ValueError(f"object '{item.id}' cannot contain itself")
        for relationship in self.relationships:
            missing = {relationship.source, relationship.target} - known
            if missing:
                raise ValueError(
                    f"relationship '{relationship.id}' references unknown objects: "
                    + ", ".join(sorted(missing))
                )
        for constraint in self.constraints:
            missing = set(constraint.object_ids) - known
            if missing:
                raise ValueError(
                    f"constraint '{constraint.id}' references unknown objects: "
                    + ", ".join(sorted(missing))
                )
        for group in self.groups:
            missing = set(group.object_ids) - known
            if missing:
                raise ValueError(
                    f"group '{group.id}' references unknown objects: "
                    + ", ".join(sorted(missing))
                )

        parents = {item.id: item.parent_id for item in self.objects}
        for start in object_ids:
            seen: set[str] = set()
            current: str | None = start
            while current is not None:
                if current in seen:
                    raise ValueError(f"containment cycle includes object '{current}'")
                seen.add(current)
                current = parents.get(current)

        ordering = [
            constraint.object_ids
            for constraint in self.constraints
            if constraint.kind == "ordering" and constraint.strength == "hard"
        ]
        successors: dict[str, set[str]] = {item: set() for item in object_ids}
        for sequence in ordering:
            for before, after in zip(sequence, sequence[1:], strict=False):
                successors[before].add(after)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(item: str) -> None:
            if item in visiting:
                raise ValueError(f"contradictory hard ordering constraints include '{item}'")
            if item in visited:
                return
            visiting.add(item)
            for successor in successors[item]:
                visit(successor)
            visiting.remove(item)
            visited.add(item)

        for item in object_ids:
            visit(item)
        return self

    def design_input(self) -> str:
        """Return a stable complete input for the downstream visual designer."""

        return (
            "Create a visual construction for this validated DiagramSpecification. "
            "Preserve every required item, explicit unknown, and hard constraint.\n\n"
            + json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True)
        )


def load_specification(path: str | Path) -> DiagramSpecification:
    """Load strict JSON or safe YAML without executing custom YAML constructors."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SpecificationError(f"could not read specification file: {error}") from error
    try:
        if source.suffix.lower() == ".json":
            value = json.loads(text)
        elif source.suffix.lower() in {".yaml", ".yml"}:
            value = yaml.safe_load(text)
        else:
            raise SpecificationError("specification file must use .json, .yaml, or .yml")
        return DiagramSpecification.model_validate(value)
    except SpecificationError:
        raise
    except (json.JSONDecodeError, yaml.YAMLError, ValueError) as error:
        raise SpecificationError(f"invalid specification: {error}") from error
