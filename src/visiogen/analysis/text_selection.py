"""Bounded deterministic selection of document prose relevant to one diagram."""

from __future__ import annotations

import re
from collections import defaultdict

from visiogen.analysis.claims import SelectedTextBlock, SelectionReason, TextSelection
from visiogen.analysis.semantics import AnalyzedDiagram
from visiogen.documents.models import DocumentSnapshot, NormalizedBox, TextBlock

_FIGURE = re.compile(r"\b(?:figure|fig\.)\s*([A-Za-z0-9.-]+)", re.IGNORECASE)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_term(text: str, term: str) -> bool:
    normalized_text = _normalized(text)
    normalized_term = _normalized(term)
    return (
        re.search(rf"(?<!\w){re.escape(normalized_term)}(?!\w)", normalized_text)
        is not None
    )


def _near_region(block: TextBlock, pages: set[int], region: NormalizedBox | None) -> bool:
    if block.location.page_number not in pages:
        return False
    if region is None or block.location.bbox is None:
        return False
    box = block.location.bbox
    vertical_gap = max(region.top - box.bottom, box.top - region.bottom, 0)
    return vertical_gap <= 0.2


def select_relevant_text(
    snapshot: DocumentSnapshot,
    diagram: AnalyzedDiagram,
    *,
    candidate_asset_ids: set[str] | None = None,
    candidate_page_numbers: set[int] | None = None,
    candidate_region: NormalizedBox | None = None,
    explicit_block_ids: set[str] | None = None,
    proximity_window: int = 2,
    max_blocks: int = 24,
    max_characters: int = 24_000,
) -> TextSelection:
    """Select exact blocks by anchors, captions, labels, references, and proximity."""

    if proximity_window < 0 or max_blocks <= 0 or max_characters <= 0:
        raise ValueError("Text-selection limits and proximity window are invalid")
    assets = candidate_asset_ids or set()
    pages = candidate_page_numbers or set()
    explicit = explicit_block_ids or set()
    known_blocks = {item.id for item in snapshot.text_blocks}
    if explicit - known_blocks:
        raise ValueError("Explicit text selection references an unknown block")
    reasons: dict[str, set[SelectionReason]] = defaultdict(set)
    anchors: set[int] = set()
    labels = [item.visible_label for item in diagram.objects if item.visible_label]
    labels.extend(
        item.visible_label for item in diagram.relationships if item.visible_label
    )
    if diagram.title:
        labels.append(diagram.title)
    references = [value for item in diagram.objects for value in item.reference_numbers]

    for block in snapshot.text_blocks:
        if block.id in explicit:
            reasons[block.id].add("explicit")
        if block.location.asset_id in assets:
            reasons[block.id].add("asset_anchor")
            anchors.add(block.order)
        if _near_region(block, pages, candidate_region):
            reasons[block.id].add("proximity")
            anchors.add(block.order)
        if any(_contains_term(block.text, label) for label in labels):
            reasons[block.id].add("label_match")
        if any(_contains_term(block.text, value) for value in references):
            reasons[block.id].add("reference_match")
        if block.origin == "caption" and (
            block.location.asset_id in assets or _near_region(block, pages, candidate_region)
        ):
            reasons[block.id].add("caption")
            anchors.add(block.order)

    for block in snapshot.text_blocks:
        if any(abs(block.order - anchor) <= proximity_window for anchor in anchors):
            reasons[block.id].add("proximity")

    figure_tokens = {
        match.group(1).casefold().strip(".")
        for block in snapshot.text_blocks
        if block.id in reasons and "caption" in reasons[block.id]
        for match in _FIGURE.finditer(block.text)
    }
    if figure_tokens:
        for block in snapshot.text_blocks:
            if any(
                match.group(1).casefold().strip(".") in figure_tokens
                for match in _FIGURE.finditer(block.text)
            ):
                reasons[block.id].add("figure_reference")

    selected: list[SelectedTextBlock] = []
    omitted: list[str] = []
    characters = 0
    for block in sorted(snapshot.text_blocks, key=lambda item: (item.order, item.id)):
        if block.id not in reasons:
            continue
        if len(selected) >= max_blocks or characters + len(block.text) > max_characters:
            omitted.append(block.id)
            continue
        selected.append(
            SelectedTextBlock(
                block_id=block.id,
                text=block.text,
                origin=block.origin,
                order=block.order,
                location=block.location,
                reasons=sorted(reasons[block.id]),
            )
        )
        characters += len(block.text)
    return TextSelection(
        source_id=snapshot.source_id,
        candidate_id=diagram.candidate_id,
        blocks=selected,
        omitted_block_ids=omitted,
        max_blocks=max_blocks,
        max_characters=max_characters,
        selected_characters=characters,
    )
