"""Deterministic A3 accuracy metrics against reviewed semantic fixtures."""

from __future__ import annotations

from visiogen.analysis.models import AnalysisModel
from visiogen.analysis.semantics import AnalyzedDiagram, AnalyzedRelationship


class SemanticCaseScore(AnalysisModel):
    """Exact-match counts for one reviewed semantic fixture."""

    case_id: str
    expected_objects: int
    predicted_objects: int
    matched_objects: int
    unexpected_object_labels: list[str]
    missing_object_labels: list[str]
    expected_references: int
    matched_references: int
    expected_edges: int
    predicted_edges: int
    matched_edges: int
    endpoint_matched_edges: int
    direction_matched_edges: int
    family_correct: bool
    ambiguous_direction_safe: bool | None


class SemanticCorpusScore(AnalysisModel):
    """Aggregate precision, recall, direction, reference, family, and ambiguity metrics."""

    object_precision: float
    object_recall: float
    reference_recall: float
    edge_precision: float
    edge_recall: float
    direction_accuracy: float
    family_accuracy: float
    ambiguous_direction_safe: int
    ambiguous_direction_total: int
    cases: list[SemanticCaseScore]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _edge_endpoints(
    relationship: AnalyzedRelationship,
    label_by_id: dict[str, str],
) -> tuple[str, str] | None:
    if relationship.source_id not in label_by_id or relationship.target_id not in label_by_id:
        return None
    source = label_by_id[relationship.source_id]
    target = label_by_id[relationship.target_id]
    if relationship.direction == "reverse":
        return target, source
    return source, target


def score_semantic_case(case: dict, diagram: AnalyzedDiagram) -> SemanticCaseScore:
    """Score exact visible labels and normalized relationship propositions."""

    expected_labels = {item["label"] for item in case["objects"]}
    allowed = set(case.get("allowed_additional_object_labels", []))
    predicted_labels = {
        item.visible_label for item in diagram.objects if item.visible_label is not None
    }
    scored_predictions = predicted_labels - allowed
    matched_labels = expected_labels & scored_predictions
    expected_references = {
        (item["label"], reference)
        for item in case["objects"]
        for reference in item["references"]
    }
    predicted_references = {
        (item.visible_label, reference)
        for item in diagram.objects
        if item.visible_label is not None
        for reference in item.reference_numbers
    }
    label_by_id = {
        item.id: item.visible_label
        for item in diagram.objects
        if item.visible_label is not None
    }
    predicted_edges: list[tuple[str, str, str]] = []
    for relationship in diagram.relationships:
        endpoints = _edge_endpoints(relationship, label_by_id)
        if endpoints is not None:
            direction = "forward" if relationship.direction == "reverse" else relationship.direction
            predicted_edges.append((endpoints[0], endpoints[1], direction))
    expected_edges = [
        (item["source"], item["target"], item["direction"])
        for item in case["relationships"]
    ]

    def endpoint_key(edge: tuple[str, str, str]) -> tuple[str, str] | frozenset[str]:
        if edge[2] in {"bidirectional", "unclear", "none"}:
            return frozenset((edge[0], edge[1]))
        return edge[0], edge[1]

    expected_by_endpoints = {endpoint_key(edge): edge for edge in expected_edges}
    predicted_by_endpoints = {endpoint_key(edge): edge for edge in predicted_edges}
    shared_endpoints = set(expected_by_endpoints) & set(predicted_by_endpoints)
    direction_matches = sum(
        expected_by_endpoints[key][2] == predicted_by_endpoints[key][2]
        for key in shared_endpoints
    )
    matched_edges = direction_matches
    ambiguous_safe: bool | None = None
    if case["ambiguous_direction"]:
        ambiguous_safe = any(
            edge[2] == "unclear"
            and endpoint_key(edge) == endpoint_key(expected_edges[0])
            for edge in predicted_edges
        )
    return SemanticCaseScore(
        case_id=case["id"],
        expected_objects=len(expected_labels),
        predicted_objects=len(scored_predictions),
        matched_objects=len(matched_labels),
        unexpected_object_labels=sorted(scored_predictions - expected_labels),
        missing_object_labels=sorted(expected_labels - scored_predictions),
        expected_references=len(expected_references),
        matched_references=len(expected_references & predicted_references),
        expected_edges=len(expected_edges),
        predicted_edges=len(predicted_edges),
        matched_edges=matched_edges,
        endpoint_matched_edges=len(shared_endpoints),
        direction_matched_edges=direction_matches,
        family_correct=diagram.family in case["accepted_families"],
        ambiguous_direction_safe=ambiguous_safe,
    )


def aggregate_semantic_scores(scores: list[SemanticCaseScore]) -> SemanticCorpusScore:
    """Aggregate case counts without averaging small and large diagrams equally."""

    expected_objects = sum(item.expected_objects for item in scores)
    predicted_objects = sum(item.predicted_objects for item in scores)
    matched_objects = sum(item.matched_objects for item in scores)
    expected_references = sum(item.expected_references for item in scores)
    matched_references = sum(item.matched_references for item in scores)
    expected_edges = sum(item.expected_edges for item in scores)
    predicted_edges = sum(item.predicted_edges for item in scores)
    matched_edges = sum(item.matched_edges for item in scores)
    endpoint_edges = sum(item.endpoint_matched_edges for item in scores)
    direction_edges = sum(item.direction_matched_edges for item in scores)
    ambiguous = [
        item.ambiguous_direction_safe
        for item in scores
        if item.ambiguous_direction_safe is not None
    ]
    return SemanticCorpusScore(
        object_precision=_ratio(matched_objects, predicted_objects),
        object_recall=_ratio(matched_objects, expected_objects),
        reference_recall=_ratio(matched_references, expected_references),
        edge_precision=_ratio(matched_edges, predicted_edges),
        edge_recall=_ratio(matched_edges, expected_edges),
        direction_accuracy=_ratio(direction_edges, endpoint_edges),
        family_accuracy=_ratio(sum(item.family_correct for item in scores), len(scores)),
        ambiguous_direction_safe=sum(value is True for value in ambiguous),
        ambiguous_direction_total=len(ambiguous),
        cases=scores,
    )
