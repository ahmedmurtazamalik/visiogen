"""A8 cross-file execution, review, and hardening evidence tests."""

from visiogen.analysis.release_evaluation import CaseReview, ReleaseCase
from visiogen.analysis.release_execution import validate_release_evidence

SOURCE_SHA = "a" * 64
BUNDLE_SHA = "b" * 64
REVISION = "c" * 40


def _case() -> ReleaseCase:
    return ReleaseCase.model_validate(
        {
            "id": "held-pdf",
            "subset": "held_out",
            "document_kind": "pdf",
            "source_path": "sources/input.pdf",
            "source_sha256": SOURCE_SHA,
            "clean_input": True,
            "coverage_tags": ["clean_native_text_pdf"],
        }
    )


def _review() -> CaseReview:
    return CaseReview.model_validate(
        {
            "case_id": "held-pdf",
            "analysis_bundle_sha256": BUNDLE_SHA,
            "diagram": {
                "reviewer_id": "diagram-reviewer",
                "prose_was_hidden": True,
                "schema_reference_valid": True,
                "expected_visible_labels": 1,
                "correct_visible_labels": 1,
                "invented_visible_labels_or_references": 0,
                "object_relationship_true_positive": 1,
                "object_relationship_false_positive": 0,
                "object_relationship_false_negative": 0,
                "forced_unclear_directions": 0,
                "unsupported_inferences": 0,
            },
            "consistency": {
                "reviewer_id": "consistency-reviewer",
                "confirmed_contradiction_true_positive": 0,
                "confirmed_contradiction_false_positive": 0,
                "confirmed_contradiction_false_negative": 0,
                "reported_contradictions": 0,
                "contradictions_with_valid_dual_evidence": 0,
                "non_exhaustive_omission_false_positives": 0,
            },
        }
    )


def _execution() -> dict:
    return {
        "status": "passed",
        "complete_corpus": True,
        "source_clean": True,
        "source_revision": REVISION,
        "provider": "codex-cli",
        "model": "gpt-5.6-sol",
        "cases": [
            {
                "case_id": "held-pdf",
                "status": "complete",
                "source_sha256": SOURCE_SHA,
                "bundle_sha256": BUNDLE_SHA,
            }
        ],
    }


def test_release_evidence_binds_reviews_to_execution_and_hardening_revision() -> None:
    validation = validate_release_evidence(
        [_case()], [_review()], _execution(), {"status": "passed", "source_clean": True, "source_revision": REVISION}
    )

    assert validation.valid
    assert validation.provider == "codex-cli"
    assert validation.model == "gpt-5.6-sol"


def test_release_evidence_rejects_revision_bundle_and_case_mismatches() -> None:
    execution = _execution()
    execution["source_revision"] = "d" * 40
    execution["cases"][0]["bundle_sha256"] = "e" * 64
    execution["cases"][0]["status"] = "partial"
    validation = validate_release_evidence(
        [_case()], [_review()], execution, {"status": "passed", "source_clean": True, "source_revision": REVISION}
    )

    assert not validation.valid
    assert any("same source revision" in item for item in validation.failures)
    assert any("not complete" in item for item in validation.failures)
    assert any("review bundle hash mismatch" in item for item in validation.failures)


def test_release_evidence_rejects_incomplete_dirty_or_missing_provenance() -> None:
    execution = _execution()
    execution.update(status="exploratory", complete_corpus=False, source_clean=False, provider="", model="")
    validation = validate_release_evidence(
        [_case()], [_review()], execution, {"status": "failed", "source_clean": False, "source_revision": REVISION}
    )

    assert not validation.valid
    assert any("passing complete-corpus" in item for item in validation.failures)
    assert any("clean source" in item for item in validation.failures)
    assert any("hardening evidence" in item for item in validation.failures)
    assert any("provider identity" in item for item in validation.failures)
    assert any("model identity" in item for item in validation.failures)
