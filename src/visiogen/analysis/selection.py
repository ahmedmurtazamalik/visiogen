"""Deterministic candidate enumeration, classification, and selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Protocol

from visiogen.analysis.errors import CandidateClassificationError
from visiogen.analysis.deduplication import find_embedded_page_duplicates
from visiogen.analysis.models import (
    CandidateCoverage,
    CandidateDecision,
    CandidateDiscovery,
    DiagramCandidate,
    DuplicateMatch,
)
from visiogen.documents.models import DocumentSnapshot, TextBlock, VisualAsset
from visiogen.documents.safety import DEFAULT_SAFETY_LIMITS, DocumentSafetyLimits

_DIAGRAM_CUE = re.compile(
    r"\b(?:diagram|schematic|architecture|flowchart|topology|process flow|"
    r"network map|block diagram)\b",
    re.IGNORECASE,
)
_MIN_CANDIDATE_EDGE = 32
_MIN_CANDIDATE_PIXELS = 4_096


class CandidateClassifier(Protocol):
    """Narrow provider-independent boundary for structured visual classification."""

    def classify(
        self,
        candidates: tuple[DiagramCandidate, ...],
    ) -> tuple[CandidateDecision, ...]:
        """Return exactly one strict decision for every supplied candidate."""


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    """Explicit candidate filters applied after classification."""

    page_number: int | None = None
    candidate_id: str | None = None
    def __post_init__(self) -> None:
        if self.page_number is not None and self.page_number <= 0:
            raise ValueError("page_number must be positive")


def _asset_groups(
    snapshot: DocumentSnapshot,
    visual_matches: tuple[DuplicateMatch, ...],
) -> list[tuple[list[VisualAsset], list[DuplicateMatch]]]:
    groups: list[tuple[list[VisualAsset], list[DuplicateMatch]]] = []
    for asset in snapshot.visual_assets:
        group = next(
            (
                assets
                for assets, _ in groups
                if assets[0].sha256 == asset.sha256
                and not (
                    asset.origin == "page_render"
                    and any(
                        item.origin == "page_render"
                        and item.location.page_number != asset.location.page_number
                        for item in assets
                    )
                )
            ),
            None,
        )
        if group is None:
            groups.append(([asset], []))
        else:
            first = group[0]
            group.append(asset)
            evidence = next(matches for assets, matches in groups if assets is group)
            evidence.append(
                DuplicateMatch(
                    first_asset_id=first.id,
                    second_asset_id=asset.id,
                    method="exact_sha256",
                    similarity=1,
                )
            )
    for match in visual_matches:
        first_group = next(
            item for item in groups if any(asset.id == match.first_asset_id for asset in item[0])
        )
        second_group = next(
            item for item in groups if any(asset.id == match.second_asset_id for asset in item[0])
        )
        if first_group is second_group:
            first_group[1].append(match)
            continue
        first_group[0].extend(second_group[0])
        first_group[1].extend(second_group[1])
        first_group[1].append(match)
        groups.remove(second_group)
    return groups


def _primary_asset(group: list[VisualAsset]) -> VisualAsset:
    # An embedded original normally retains more label detail than a page render.
    return min(group, key=lambda asset: (asset.origin != "embedded", group.index(asset)))


def _linked_text(snapshot: DocumentSnapshot, asset_ids: set[str]) -> list[TextBlock]:
    return [
        block
        for block in snapshot.text_blocks
        if block.location.asset_id in asset_ids and block.origin in {"caption", "alt_text"}
    ]


def _mechanical_decision(
    candidate_id: str,
    primary: VisualAsset,
    linked_text: list[TextBlock],
) -> CandidateDecision:
    assert primary.width_px is not None and primary.height_px is not None
    if (
        min(primary.width_px, primary.height_px) < _MIN_CANDIDATE_EDGE
        or primary.width_px * primary.height_px < _MIN_CANDIDATE_PIXELS
    ):
        return CandidateDecision(
            candidate_id=candidate_id,
            label="non_diagram",
            confidence="high",
            reason="Asset is below the minimum useful visual dimensions",
            classifier="mechanical-size-policy-v1",
        )
    cue = next((block.text for block in linked_text if _DIAGRAM_CUE.search(block.text)), None)
    if cue is not None:
        return CandidateDecision(
            candidate_id=candidate_id,
            label="diagram",
            confidence="medium",
            reason=f"Linked caption or alt text contains a diagram cue: {cue}",
            classifier="mechanical-linked-text-v1",
        )
    return CandidateDecision(
        candidate_id=candidate_id,
        label="unknown",
        confidence="unknown",
        reason="Visual classification is required; no decisive mechanical evidence exists",
        classifier="mechanical-enumeration-v1",
    )


def _enumerate(
    snapshot: DocumentSnapshot,
    visual_matches: tuple[DuplicateMatch, ...],
) -> list[DiagramCandidate]:
    candidates: list[DiagramCandidate] = []
    for index, (group, duplicate_matches) in enumerate(
        _asset_groups(snapshot, visual_matches),
        start=1,
    ):
        primary = _primary_asset(group)
        if primary.width_px is None or primary.height_px is None:
            # A1 currently emits dimensions for supported assets, but retain an honest state.
            raise CandidateClassificationError(
                f"Visual asset has no dimensions: {primary.id}"
            )
        candidate_id = f"candidate-{index:04d}"
        source_ids = [asset.id for asset in group]
        decision = _mechanical_decision(
            candidate_id,
            primary,
            _linked_text(snapshot, set(source_ids)),
        )
        disposition = {
            "diagram": "selected",
            "non_diagram": "ignored_non_diagram",
            "unknown": "awaiting_classification",
        }[decision.label]
        candidates.append(
            DiagramCandidate(
                id=candidate_id,
                primary_asset_id=primary.id,
                source_asset_ids=source_ids,
                page_number=next(
                    (
                        asset.location.page_number
                        for asset in group
                        if asset.location.page_number is not None
                    ),
                    None,
                ),
                width_px=primary.width_px,
                height_px=primary.height_px,
                duplicate_matches=duplicate_matches,
                decision=decision,
                disposition=disposition,
                disposition_reason=decision.reason,
            )
        )
    return candidates


def _apply_classifier(
    candidates: list[DiagramCandidate],
    classifier: CandidateClassifier | None,
) -> list[DiagramCandidate]:
    if classifier is None:
        return candidates
    eligible = [
        candidate
        for candidate in candidates
        if candidate.decision.classifier != "mechanical-size-policy-v1"
    ]
    if not eligible:
        return candidates
    try:
        decisions = classifier.classify(tuple(eligible))
    except CandidateClassificationError:
        raise
    except Exception as error:
        raise CandidateClassificationError("Candidate classifier failed") from error
    expected = {candidate.id for candidate in eligible}
    returned = [decision.candidate_id for decision in decisions]
    if len(returned) != len(set(returned)) or set(returned) != expected:
        raise CandidateClassificationError(
            "Classifier must return exactly one decision for every candidate"
        )
    by_id = {decision.candidate_id: decision for decision in decisions}
    classified: list[DiagramCandidate] = []
    for candidate in candidates:
        decision = by_id.get(candidate.id)
        if decision is None:
            classified.append(candidate)
            continue
        disposition = {
            "diagram": "selected",
            "non_diagram": "ignored_non_diagram",
            "unknown": "awaiting_classification",
        }[decision.label]
        classified.append(
            candidate.model_copy(
                update={
                    "decision": decision,
                    "disposition": disposition,
                    "disposition_reason": decision.reason,
                }
            )
        )
    return classified


def _apply_selection(
    candidates: list[DiagramCandidate],
    selection: CandidateSelection,
    max_candidates: int,
) -> list[DiagramCandidate]:
    if selection.candidate_id is not None and not any(
        candidate.id == selection.candidate_id for candidate in candidates
    ):
        raise CandidateClassificationError(
            f"Requested candidate does not exist: {selection.candidate_id}"
        )
    selected_count = 0
    output: list[DiagramCandidate] = []
    for candidate in candidates:
        if selection.page_number is not None and candidate.page_number != selection.page_number:
            output.append(
                candidate.model_copy(
                    update={
                        "disposition": "filtered_out",
                        "disposition_reason": "Candidate is outside the requested page",
                    }
                )
            )
            continue
        if selection.candidate_id is not None and candidate.id != selection.candidate_id:
            output.append(
                candidate.model_copy(
                    update={
                        "disposition": "filtered_out",
                        "disposition_reason": "A different candidate was explicitly requested",
                    }
                )
            )
            continue
        should_select = candidate.decision.label == "diagram"
        if selection.candidate_id == candidate.id and candidate.decision.label == "unknown":
            should_select = True
        if not should_select:
            output.append(candidate)
            continue
        if selected_count >= max_candidates:
            output.append(
                candidate.model_copy(
                    update={
                        "disposition": "skipped_limit",
                        "disposition_reason": "Configured diagram candidate limit was reached",
                    }
                )
            )
            continue
        selected_count += 1
        output.append(
            candidate.model_copy(
                update={
                    "disposition": "selected",
                    "disposition_reason": (
                        "Candidate was explicitly selected"
                        if selection.candidate_id == candidate.id
                        else "Candidate was classified as a diagram"
                    ),
                }
            )
        )
    return output


def discover_diagram_candidates(
    snapshot: DocumentSnapshot,
    *,
    snapshot_dir: str | Path | None = None,
    classifier: CandidateClassifier | None = None,
    selection: CandidateSelection = CandidateSelection(),
    limits: DocumentSafetyLimits = DEFAULT_SAFETY_LIMITS,
) -> CandidateDiscovery:
    """Enumerate, deduplicate, classify, select, and account for every visual asset."""

    visual_matches = (
        find_embedded_page_duplicates(snapshot, snapshot_dir, limits=limits)
        if snapshot_dir is not None
        else ()
    )
    candidates = _enumerate(snapshot, visual_matches)
    candidates = _apply_classifier(candidates, classifier)
    candidates = _apply_selection(candidates, selection, limits.max_diagram_candidates)
    counts = {name: 0 for name in (
        "selected",
        "ignored_non_diagram",
        "awaiting_classification",
        "filtered_out",
        "skipped_limit",
    )}
    for candidate in candidates:
        counts[candidate.disposition] += 1
    coverage = CandidateCoverage(
        source_assets=len(snapshot.visual_assets),
        unique_candidates=len(candidates),
        duplicate_assets_grouped=len(snapshot.visual_assets) - len(candidates),
        **counts,
    )
    return CandidateDiscovery(
        source_id=snapshot.source_id,
        candidates=candidates,
        coverage=coverage,
    )
