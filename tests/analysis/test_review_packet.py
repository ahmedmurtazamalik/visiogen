"""A8 blinded-review packet generation tests."""

import pytest

from visiogen.analysis.release_evaluation import ReleaseCase
from visiogen.analysis.review_packet import build_review_packet

SHA = "a" * 64
BUNDLE = "b" * 64


def _case(case_id: str, subset: str) -> ReleaseCase:
    return ReleaseCase.model_validate(
        {
            "id": case_id,
            "subset": subset,
            "document_kind": "pdf",
            "source_path": f"sources/{case_id}.pdf",
            "source_sha256": SHA if subset == "held_out" else "c" * 64,
            "clean_input": True,
            "coverage_tags": ["clean_native_text_pdf"],
        }
    )


def _execution() -> dict:
    return {
        "status": "passed",
        "complete_corpus": True,
        "source_revision": "d" * 40,
        "provider": "codex-cli",
        "model": "gpt-5.6-sol",
        "cases": [
            {
                "case_id": "development",
                "status": "complete",
                "bundle_sha256": "e" * 64,
            },
            {
                "case_id": "held-out",
                "status": "complete",
                "bundle_sha256": BUNDLE,
            },
        ],
    }


def test_review_packet_contains_only_held_out_forms_and_exact_bundle_hash() -> None:
    packet = build_review_packet(
        [_case("development", "development"), _case("held-out", "held_out")],
        _execution(),
    )

    assert packet["source_revision"] == "d" * 40
    assert [review["case_id"] for review in packet["reviews"]] == ["held-out"]
    review = packet["reviews"][0]
    assert review["analysis_bundle_sha256"] == BUNDLE
    assert review["diagram"]["prose_was_hidden"] is None
    assert review["diagram"]["reviewer_id"] is None
    assert review["consistency"]["reviewer_id"] is None
    assert "Hide all document prose" in packet["instructions"]["diagram_pass"]


@pytest.mark.parametrize(
    "mutation, message",
    [
        ({"status": "failed"}, "passing complete-corpus"),
        ({"complete_corpus": False}, "passing complete-corpus"),
        ({"cases": []}, "exactly match"),
    ],
)
def test_review_packet_rejects_incomplete_or_mismatched_execution(mutation, message) -> None:
    execution = _execution()
    execution.update(mutation)

    with pytest.raises(ValueError, match=message):
        build_review_packet(
            [_case("development", "development"), _case("held-out", "held_out")],
            execution,
        )


def test_review_packet_rejects_partial_or_unhashed_held_out_case() -> None:
    execution = _execution()
    execution["cases"][1]["status"] = "partial"
    execution["cases"][1]["bundle_sha256"] = None

    with pytest.raises(ValueError, match="not complete and hash-bound"):
        build_review_packet(
            [_case("development", "development"), _case("held-out", "held_out")],
            execution,
        )
