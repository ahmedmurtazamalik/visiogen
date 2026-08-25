"""Bounded A5 relevant-prose selection and accounting."""

from visiogen.analysis.semantics import AnalyzedDiagram
from visiogen.analysis.text_selection import select_relevant_text
from visiogen.documents.models import (
    CoverageReport,
    DocumentSnapshot,
    SourceLocation,
    TextBlock,
    VisualAsset,
)


def _block(
    block_id: str,
    text: str,
    order: int,
    *,
    origin: str = "native",
    asset_id: str | None = None,
) -> TextBlock:
    return TextBlock.model_validate(
        {
            "id": block_id,
            "text": text,
            "origin": origin,
            "order": order,
            "location": {
                "block_id": block_id,
                "paragraph_index": order,
                "asset_id": asset_id,
            },
        }
    )


def _snapshot() -> DocumentSnapshot:
    return DocumentSnapshot(
        source_id="source-1",
        source_sha256="1" * 64,
        source_name="claims.docx",
        document_kind="docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        byte_size=100,
        text_blocks=[
            _block("text-0001", "Unrelated introduction.", 0),
            _block("text-0002", "The Sensor 10 monitors temperature.", 1),
            _block(
                "text-0003",
                "Figure 2. Control architecture",
                2,
                origin="caption",
                asset_id="asset-1",
            ),
            _block("text-0004", "In Figure 2, Processor 20 receives the reading.", 3),
            _block("text-0005", "Unrelated conclusion.", 4),
            _block("text-0006", "See Figure 9 for deployment.", 5),
        ],
        visual_assets=[
            VisualAsset(
                id="asset-1",
                media_type="image/png",
                origin="embedded",
                sha256="2" * 64,
                byte_size=10,
                artifact_path="assets/diagram.png",
                width_px=100,
                height_px=100,
                location=SourceLocation(relationship_id="rId1"),
            )
        ],
        coverage=CoverageReport(
            native_text="complete",
            embedded_media="complete",
            rendered_pages="not_available",
        ),
    )


def _diagram() -> AnalyzedDiagram:
    return AnalyzedDiagram.model_validate(
        {
            "candidate_id": "candidate-0001",
            "family": "system_block",
            "orientation": "left_to_right",
            "objects": [
                {
                    "id": "object-0001",
                    "visible_label": "Sensor 10",
                    "normalized_label": "sensor 10",
                    "semantic_type": "sensor",
                    "visual_shape": "rectangle",
                    "reference_numbers": ["10"],
                    "bbox": {"left": 0.1, "top": 0.2, "right": 0.3, "bottom": 0.4},
                    "evidence_ids": ["evidence-0001"],
                    "confidence": "high",
                },
                {
                    "id": "object-0002",
                    "visible_label": "Processor 20",
                    "normalized_label": "processor 20",
                    "semantic_type": "processor",
                    "visual_shape": "rectangle",
                    "reference_numbers": ["20"],
                    "bbox": {"left": 0.6, "top": 0.2, "right": 0.8, "bottom": 0.4},
                    "evidence_ids": ["evidence-0002"],
                    "confidence": "high",
                },
            ],
            "relationships": [],
            "confidence": "high",
        }
    )


def test_selection_combines_anchor_caption_proximity_figure_and_label_reasons() -> None:
    selection = select_relevant_text(
        _snapshot(),
        _diagram(),
        candidate_asset_ids={"asset-1"},
        proximity_window=1,
    )

    assert [item.block_id for item in selection.blocks] == [
        "text-0002",
        "text-0003",
        "text-0004",
    ]
    reasons = {item.block_id: set(item.reasons) for item in selection.blocks}
    assert reasons["text-0002"] == {"label_match", "reference_match", "proximity"}
    assert reasons["text-0003"] == {
        "asset_anchor",
        "caption",
        "figure_reference",
        "proximity",
    }
    assert "figure_reference" in reasons["text-0004"]
    assert "text-0006" not in reasons


def test_selection_never_truncates_and_accounts_for_limit_omissions() -> None:
    selection = select_relevant_text(
        _snapshot(),
        _diagram(),
        candidate_asset_ids={"asset-1"},
        proximity_window=1,
        max_blocks=2,
        max_characters=200,
    )

    assert [item.block_id for item in selection.blocks] == ["text-0002", "text-0003"]
    assert selection.omitted_block_ids == ["text-0004"]
    assert selection.selected_characters == sum(len(item.text) for item in selection.blocks)


def test_explicit_selection_rejects_unknown_blocks() -> None:
    try:
        select_relevant_text(
            _snapshot(),
            _diagram(),
            explicit_block_ids={"missing"},
        )
    except ValueError as error:
        assert "unknown block" in str(error)
    else:
        raise AssertionError("unknown explicit block was accepted")


def test_selection_uses_title_and_relationship_labels_with_token_boundaries() -> None:
    snapshot = _snapshot().model_copy(
        update={
            "text_blocks": [
                _block("text-0001", "Control architecture is detailed below.", 0),
                _block("text-0002", "The commands path is mandatory.", 1),
                _block("text-0003", "A Biosensor is discussed elsewhere.", 2),
            ]
        }
    )
    payload = _diagram().model_dump(mode="json")
    payload["title"] = "Control architecture"
    payload["title_evidence_ids"] = ["evidence-0001"]
    payload["objects"][0]["visible_label"] = "Sensor"
    payload["objects"][0]["normalized_label"] = "sensor"
    payload["relationships"] = [
        {
            "id": "relationship-0001",
            "source_id": "object-0001",
            "target_id": "object-0002",
            "source_certainty": "known",
            "target_certainty": "known",
            "direction": "forward",
            "relation": "control",
            "visible_label": "commands",
            "normalized_label": "commands",
            "path": [{"x": 0.3, "y": 0.3}, {"x": 0.6, "y": 0.3}],
            "line_style": "solid",
            "evidence_ids": ["evidence-0002"],
            "confidence": "high",
        }
    ]

    selection = select_relevant_text(snapshot, AnalyzedDiagram.model_validate(payload))

    assert [item.block_id for item in selection.blocks] == ["text-0001", "text-0002"]
    assert all(item.reasons == ["label_match"] for item in selection.blocks)
