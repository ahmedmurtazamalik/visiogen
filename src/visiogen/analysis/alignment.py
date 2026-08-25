"""Conservative deterministic entity alignment with unresolved alternatives."""

from __future__ import annotations

from difflib import SequenceMatcher
import re

from visiogen.analysis.claim_validation import normalize_claim_text
from visiogen.analysis.claims import (
    AlignmentAlternative,
    DocumentClaim,
    DocumentClaimBatch,
    EntityAlignment,
    EntityAlignmentSet,
)
from visiogen.analysis.semantics import AnalyzedDiagram, AnalyzedObject

_OBJECT_VALUE_PREDICATES = {"alias", "contains", "connects_to", "sequence"}


def _reference_matches(entity: str, objects: list[AnalyzedObject]) -> list[AnalyzedObject]:
    return [
        item
        for item in objects
        if any(
            re.search(rf"(?<!\w){re.escape(value.casefold())}(?!\w)", entity)
            for value in item.reference_numbers
        )
    ]


def _exact_label_matches(entity: str, objects: list[AnalyzedObject]) -> list[AnalyzedObject]:
    return [item for item in objects if item.normalized_label == entity]


def _fuzzy_candidates(
    entity: str,
    objects: list[AnalyzedObject],
) -> list[tuple[float, AnalyzedObject]]:
    if len(entity) <= 3:
        return []
    threshold = 0.95 if len(entity) <= 5 else 0.88
    values = [
        (SequenceMatcher(None, entity, item.normalized_label or "").ratio(), item)
        for item in objects
        if item.normalized_label
    ]
    return sorted(
        (value for value in values if value[0] >= threshold),
        reverse=True,
        key=lambda value: value[0],
    )


def _align_one(
    claim: DocumentClaim,
    role: str,
    text: str,
    objects: list[AnalyzedObject],
    aliases: dict[str, str],
) -> EntityAlignment:
    entity = normalize_claim_text(text)
    evidence_ids = claim.evidence_ids
    for method, matches in (
        ("exact_reference", _reference_matches(entity, objects)),
        ("exact_label", _exact_label_matches(entity, objects)),
    ):
        if len(matches) == 1:
            return EntityAlignment(
                claim_id=claim.id,
                entity_role=role,
                entity_text=text,
                normalized_entity=entity,
                object_id=matches[0].id,
                method=method,
                score=1,
                evidence_ids=evidence_ids,
            )
        if len(matches) > 1:
            return EntityAlignment(
                claim_id=claim.id,
                entity_role=role,
                entity_text=text,
                normalized_entity=entity,
                method="unresolved",
                score=0,
                evidence_ids=evidence_ids,
                alternatives=[
                    AlignmentAlternative(
                        object_id=item.id,
                        method=method,
                        score=1,
                        reason="The exact key matches more than one diagram object",
                    )
                    for item in matches
                ],
            )
    canonical = aliases.get(entity)
    if canonical:
        matches = _exact_label_matches(canonical, objects)
        if len(matches) == 1:
            return EntityAlignment(
                claim_id=claim.id,
                entity_role=role,
                entity_text=text,
                normalized_entity=entity,
                object_id=matches[0].id,
                method="explicit_alias",
                score=1,
                evidence_ids=evidence_ids,
            )
    fuzzy = _fuzzy_candidates(entity, objects)
    if fuzzy and (len(fuzzy) == 1 or fuzzy[0][0] - fuzzy[1][0] >= 0.08):
        score, item = fuzzy[0]
        return EntityAlignment(
            claim_id=claim.id,
            entity_role=role,
            entity_text=text,
            normalized_entity=entity,
            object_id=item.id,
            method="conservative_fuzzy",
            score=score,
            evidence_ids=evidence_ids,
        )
    return EntityAlignment(
        claim_id=claim.id,
        entity_role=role,
        entity_text=text,
        normalized_entity=entity,
        method="unresolved",
        score=0,
        evidence_ids=evidence_ids,
        alternatives=[
            AlignmentAlternative(
                object_id=item.id,
                method="conservative_fuzzy",
                score=score,
                reason="Candidate did not clear the conservative uniqueness margin",
            )
            for score, item in fuzzy[:3]
        ],
    )


def align_claim_entities(
    batch: DocumentClaimBatch,
    diagram: AnalyzedDiagram,
) -> EntityAlignmentSet:
    """Align reference, label, explicit-alias, and uniquely strong fuzzy matches."""

    if batch.candidate_id != diagram.candidate_id:
        raise ValueError("Claim batch and analyzed diagram have different candidate IDs")

    aliases: dict[str, str] = {}
    for claim in batch.claims:
        if (
            claim.predicate == "alias"
            and claim.normalized_object is not None
            and claim.refers_to_candidate == "yes"
        ):
            aliases[claim.normalized_subject] = claim.normalized_object
            aliases[claim.normalized_object] = claim.normalized_subject
    alignments = []
    for claim in batch.claims:
        if claim.predicate not in {"figure_title", "figure_purpose"}:
            alignments.append(
                _align_one(claim, "subject", claim.subject_text, diagram.objects, aliases)
            )
        if claim.predicate in _OBJECT_VALUE_PREDICATES and claim.object_text is not None:
            alignments.append(
                _align_one(claim, "object", claim.object_text, diagram.objects, aliases)
            )
    return EntityAlignmentSet(candidate_id=diagram.candidate_id, alignments=alignments)
