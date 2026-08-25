"""Candidate enumeration, classification, deduplication, and selection tests."""

from visiogen.analysis.models import CandidateDecision
from visiogen.analysis.selection import CandidateSelection, discover_diagram_candidates
from visiogen.documents.models import (
    CoverageReport,
    DocumentSnapshot,
    SourceLocation,
    TextBlock,
    VisualAsset,
)
from visiogen.documents.safety import DocumentSafetyLimits


def _asset(
    asset_id: str,
    sha: str,
    *,
    origin: str = "page_render",
    width: int = 1200,
    height: int = 800,
    page: int | None = 1,
) -> VisualAsset:
    return VisualAsset(
        id=asset_id,
        media_type="image/png",
        origin=origin,
        sha256=sha,
        byte_size=100,
        artifact_path=f"assets/{asset_id}.png",
        width_px=width,
        height_px=height,
        location=SourceLocation(page_number=page),
    )


def _snapshot(
    assets: list[VisualAsset],
    text_blocks: list[TextBlock] | None = None,
) -> DocumentSnapshot:
    return DocumentSnapshot(
        source_id="sha256:" + "a" * 64,
        source_sha256="a" * 64,
        source_name="source.pdf",
        document_kind="pdf",
        media_type="application/pdf",
        byte_size=100,
        page_count=3,
        visual_assets=assets,
        text_blocks=text_blocks or [],
        coverage=CoverageReport(
            native_text="complete",
            embedded_media="not_available",
            rendered_pages="complete",
        ),
    )


class DiagramClassifier:
    def classify(self, candidates):
        return tuple(
            CandidateDecision(
                candidate_id=candidate.id,
                label="diagram",
                confidence="high",
                reason="Visible boxes and directed connectors",
                classifier="fake-vision-v1",
            )
            for candidate in candidates
        )


def test_discovery_groups_exact_duplicates_and_prefers_embedded_original() -> None:
    shared_sha = "1" * 64
    snapshot = _snapshot(
        [
            _asset("page", shared_sha),
            _asset("embedded", shared_sha, origin="embedded", page=None),
        ]
    )

    result = discover_diagram_candidates(snapshot, classifier=DiagramClassifier())

    assert result.coverage.source_assets == 2
    assert result.coverage.unique_candidates == 1
    assert result.coverage.duplicate_assets_grouped == 1
    candidate = result.candidates[0]
    assert candidate.primary_asset_id == "embedded"
    assert candidate.source_asset_ids == ["page", "embedded"]
    assert candidate.page_number == 1
    assert candidate.disposition == "selected"


def test_identical_renders_on_different_pages_remain_separate_candidates() -> None:
    snapshot = _snapshot(
        [
            _asset("page-1", "8" * 64, page=1),
            _asset("page-2", "8" * 64, page=2),
        ]
    )

    result = discover_diagram_candidates(snapshot)

    assert result.coverage.unique_candidates == 2
    assert [candidate.page_number for candidate in result.candidates] == [1, 2]


def test_mechanical_policy_rejects_tiny_assets_and_uses_linked_diagram_cues() -> None:
    tiny = _asset("tiny", "2" * 64, width=16, height=16)
    diagram = _asset("diagram", "3" * 64, origin="embedded", page=None)
    caption = TextBlock(
        id="text-1",
        text="System architecture diagram",
        origin="caption",
        order=0,
        location=SourceLocation(asset_id="diagram"),
    )

    result = discover_diagram_candidates(_snapshot([tiny, diagram], [caption]))

    assert [candidate.disposition for candidate in result.candidates] == [
        "ignored_non_diagram",
        "selected",
    ]
    assert result.coverage.ignored_non_diagram == 1
    assert result.coverage.selected == 1


def test_unknown_candidates_are_visible_and_explicit_selection_can_admit_one() -> None:
    snapshot = _snapshot([_asset("page", "4" * 64)])
    automatic = discover_diagram_candidates(snapshot)
    assert automatic.candidates[0].disposition == "awaiting_classification"

    explicit = discover_diagram_candidates(
        snapshot,
        selection=CandidateSelection(candidate_id="candidate-0001"),
    )
    assert explicit.candidates[0].disposition == "selected"
    assert explicit.candidates[0].decision.label == "unknown"


def test_page_filter_and_candidate_limit_have_explicit_dispositions() -> None:
    snapshot = _snapshot(
        [
            _asset("page-1", "5" * 64, page=1),
            _asset("page-2", "6" * 64, page=2),
            _asset("page-3", "7" * 64, page=3),
        ]
    )
    limits = DocumentSafetyLimits(max_diagram_candidates=1)
    result = discover_diagram_candidates(
        snapshot,
        classifier=DiagramClassifier(),
        selection=CandidateSelection(page_number=2),
        limits=limits,
    )

    assert [candidate.disposition for candidate in result.candidates] == [
        "filtered_out",
        "selected",
        "filtered_out",
    ]
    assert result.coverage.filtered_out == 2
