"""G0 frozen generation corpus and baseline contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from visiogen.generation.evaluation import (
    BaselineCaseResult,
    BaselineReport,
    GenerationCorpus,
    GenerationCorpusCase,
    sha256_bytes,
    validate_baseline_report,
    validate_generation_corpus,
)

CORPUS_PATH = Path("tests/fixtures/generation_v2/corpus.json")


def _corpus() -> GenerationCorpus:
    return GenerationCorpus.model_validate_json(CORPUS_PATH.read_bytes())


def test_frozen_generation_v2_corpus_has_required_coverage() -> None:
    corpus = _corpus()
    result = validate_generation_corpus(corpus)

    assert result.valid, result.failures
    assert result.case_count == 10
    assert len(result.families) == 10


def test_corpus_relationships_must_reference_declared_objects() -> None:
    data = _corpus().cases[0].model_dump(mode="json")
    data["expected_relationships"][0]["target"] = "missing"

    with pytest.raises(ValidationError, match="reference expected objects"):
        GenerationCorpusCase.model_validate(data)


def test_corpus_rejects_missing_family_and_unfrozen_state() -> None:
    corpus = _corpus().model_copy(
        update={"frozen": False, "cases": _corpus().cases[:-1]}
    )

    result = validate_generation_corpus(corpus)

    assert not result.valid
    assert any("document_reconstruction" in failure for failure in result.failures)
    assert "corpus must declare frozen=true" in result.failures


def test_measured_baseline_requires_all_artifact_hashes() -> None:
    with pytest.raises(ValidationError, match="require manifest, preview, and VSDX"):
        BaselineCaseResult(
            case_id="branching-order-fulfillment",
            evidence_state="measured",
            reason="Attempted",
        )


def test_incomplete_baseline_must_cover_exact_corpus() -> None:
    corpus = _corpus()
    report = BaselineReport(
        status="incomplete",
        source_revision="2c56b13",
        corpus_sha256="a" * 64,
        generation_test_count=168,
        generation_tests_passed=True,
        current_limitations=["Windows evidence unavailable"],
        cases=[
            BaselineCaseResult(
                case_id=corpus.cases[0].id,
                evidence_state="unavailable",
                reason="Windows evidence unavailable",
            )
        ],
    )

    failures = validate_baseline_report(corpus, report)

    assert any("baseline missing cases" in failure for failure in failures)


def test_checked_in_baseline_is_schema_valid_and_bound_to_corpus() -> None:
    report_path = Path("docs/acceptance/evidence/g0-generation-v1-baseline.json")
    report = BaselineReport.model_validate_json(report_path.read_bytes())

    assert report.status == "incomplete"
    assert report.generation_tests_passed
    assert validate_baseline_report(_corpus(), report) == []
    assert report.corpus_sha256 == sha256_bytes(CORPUS_PATH.read_bytes())
    assert json.loads(report_path.read_text())["report_version"] == 1
