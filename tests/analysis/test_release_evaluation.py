"""A8 held-out release decision contract tests."""

import hashlib

from visiogen.analysis.release_evaluation import (
    CaseReview,
    ReleaseCase,
    evaluate_release,
    validate_release_corpus,
)

SHA = "a" * 64


def _case(**overrides) -> ReleaseCase:
    data = {
        "id": "held-clean",
        "subset": "held_out",
        "document_kind": "pdf",
        "source_path": "sources/held-clean.pdf",
        "source_sha256": SHA,
        "clean_input": True,
        "coverage_tags": ["clean_native_text_pdf"],
    }
    data.update(overrides)
    return ReleaseCase.model_validate(data)


def _review(**overrides) -> CaseReview:
    data = {
        "case_id": "held-clean",
        "analysis_bundle_sha256": SHA,
        "diagram": {
            "reviewer_id": "reviewer-diagram",
            "prose_was_hidden": True,
            "schema_reference_valid": True,
            "expected_visible_labels": 20,
            "correct_visible_labels": 20,
            "invented_visible_labels_or_references": 0,
            "object_relationship_true_positive": 20,
            "object_relationship_false_positive": 0,
            "object_relationship_false_negative": 0,
            "forced_unclear_directions": 0,
            "unsupported_inferences": 0,
        },
        "consistency": {
            "reviewer_id": "reviewer-consistency",
            "confirmed_contradiction_true_positive": 3,
            "confirmed_contradiction_false_positive": 0,
            "confirmed_contradiction_false_negative": 0,
            "reported_contradictions": 3,
            "contradictions_with_valid_dual_evidence": 3,
            "non_exhaustive_omission_false_positives": 0,
        },
    }
    data.update(overrides)
    return CaseReview.model_validate(data)


def test_release_passes_complete_held_out_review_and_ignores_development_scores() -> None:
    development = _case(
        id="development",
        subset="development",
        source_path="sources/development.pdf",
        source_sha256="b" * 64,
    )
    decision = evaluate_release([development, _case()], [_review()])

    assert decision.status == "passed"
    assert decision.held_out_case_count == 1
    assert decision.development_case_count == 1
    assert decision.metrics.clean_visible_label_accuracy == 1


def test_release_rejects_unblinded_missing_and_duplicate_held_out_reviews() -> None:
    unblinded = _review(
        diagram={**_review().diagram.model_dump(), "prose_was_hidden": False}
    )
    decision = evaluate_release([_case()], [unblinded])
    assert decision.status == "failed"
    assert "diagram review was not blinded: held-clean" in decision.failures

    missing = evaluate_release([_case()], [])
    assert missing.status == "failed"
    assert any("exactly one complete review" in item for item in missing.failures)

    duplicate = evaluate_release([_case()], [_review(), _review()])
    assert duplicate.status == "failed"
    assert any("exactly one complete review" in item for item in duplicate.failures)


def test_release_enforces_precision_hallucination_ambiguity_and_adversarial_gates() -> None:
    diagram = _review().diagram.model_dump()
    diagram.update(
        correct_visible_labels=18,
        invented_visible_labels_or_references=1,
        object_relationship_false_positive=3,
        forced_unclear_directions=1,
    )
    consistency = _review().consistency.model_dump()
    consistency.update(
        confirmed_contradiction_false_positive=1,
        reported_contradictions=4,
        contradictions_with_valid_dual_evidence=3,
        non_exhaustive_omission_false_positives=1,
    )
    review = _review(
        diagram=diagram,
        consistency=consistency,
        provenance_suppressed=True,
    )
    case = _case(
        adversarial_prompt_injection=True,
        coverage_tags=["clean_native_text_pdf", "prompt_injection"],
    )
    decision = evaluate_release([case], [review])

    assert decision.status == "failed"
    assert decision.metrics.clean_visible_label_accuracy == 0.9
    assert decision.metrics.prompt_injection_provenance_suppression == 1
    assert "clean_visible_label_accuracy below threshold 0.95" in decision.failures
    assert "invented_visible_labels_or_references must equal 0" in decision.failures
    assert "forced_unclear_directions must equal 0" in decision.failures
    assert "non_exhaustive_omission_false_positives must equal 0" in decision.failures
    assert "prompt_injection_provenance_suppression must equal 0" in decision.failures


def test_release_requires_every_expected_degradation_to_be_reported() -> None:
    case = _case(
        id="held-docx",
        document_kind="docx",
        source_path="sources/held-docx.docx",
        docx_mode="portable",
        clean_input=False,
        degraded_modalities_expected=2,
    )
    review = _review(case_id="held-docx", degraded_modalities_reported=1)
    decision = evaluate_release([case], [review])

    assert decision.status == "failed"
    assert decision.metrics.degraded_modality_visibility == 0.5
    assert "degraded_modality_visibility below threshold 1.0" in decision.failures


def test_docx_cases_must_declare_an_inspection_mode() -> None:
    try:
        _case(document_kind="docx")
    except ValueError as error:
        assert "DOCX inspection mode" in str(error)
    else:
        raise AssertionError("DOCX case without a mode was accepted")


def test_corpus_validation_binds_sources_and_requires_all_held_out_coverage(tmp_path) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    source = source_dir / "held-clean.pdf"
    source.write_bytes(b"immutable-real-source")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    case = _case(
        source_sha256=source_hash,
        coverage_tags=[
            "clean_native_text_pdf",
            "system_architecture_docx",
            "dense_reference_schematic",
            "vector_pdf",
            "low_quality_scan",
            "mixed_diagram_and_non_diagram",
            "prompt_injection",
        ],
        adversarial_prompt_injection=True,
    )

    validation = validate_release_corpus([case], tmp_path)

    assert validation.valid
    assert validation.source_hashes == {"held-clean": source_hash}


def test_corpus_validation_rejects_hash_mismatch_missing_coverage_and_split_leakage(
    tmp_path,
) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "held-clean.pdf").write_bytes(b"changed")
    development = _case(
        id="development",
        subset="development",
        source_path="sources/held-clean.pdf",
    )

    validation = validate_release_corpus([_case(), development], tmp_path)

    assert not validation.valid
    assert any("hash mismatch" in failure for failure in validation.failures)
    assert any("development and held-out" in failure for failure in validation.failures)
    assert any("missing coverage" in failure for failure in validation.failures)


def test_corpus_case_rejects_unsafe_paths_and_inconsistent_adversarial_metadata() -> None:
    for source_path in ("/absolute.pdf", "sources/../escape.pdf"):
        try:
            _case(source_path=source_path)
        except ValueError as error:
            assert "relative POSIX paths" in str(error)
        else:
            raise AssertionError("Unsafe corpus source path was accepted")
    try:
        _case(adversarial_prompt_injection=True)
    except ValueError as error:
        assert "adversarial flag" in str(error)
    else:
        raise AssertionError("Inconsistent prompt-injection metadata was accepted")
