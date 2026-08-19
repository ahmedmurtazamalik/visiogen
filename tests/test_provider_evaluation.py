import hashlib
from pathlib import Path
import shutil

import pytest

from visiogen.models import DiagramGraph
from visiogen.provider_evaluation import evaluate_fixture_corpus
from visiogen.providers.base import NoDiagramContentError


FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED = FIXTURES / "graphs" / "expected"


class ReviewedFixtureExtractor:
    def extract(self, text: str) -> DiagramGraph:
        for prompt_path in (FIXTURES / "text").glob("*.txt"):
            if prompt_path.read_text() != text:
                continue
            if prompt_path.stem == "ambiguous_no_diagram":
                raise NoDiagramContentError("No diagram content")
            return DiagramGraph.model_validate_json(
                (EXPECTED / f"{prompt_path.stem}.json").read_text()
            )
        raise AssertionError("unknown prompt")


def checksums(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.glob("*.json")
    }


def test_provider_evaluation_writes_actuals_and_never_changes_reviewed_fixtures(
    tmp_path: Path,
) -> None:
    before = checksums(EXPECTED)

    report = evaluate_fixture_corpus(
        ReviewedFixtureExtractor(),
        provider="local",
        fixtures_root=FIXTURES,
        artifact_root=tmp_path,
    )

    output = tmp_path / "local"
    assert report["case_count"] == 10
    assert report["mismatch_count"] == 0
    assert len(list(output.glob("*.actual.json"))) == 9
    assert (output / "semantic-mismatch-report.json").is_file()
    assert checksums(EXPECTED) == before


def test_provider_evaluation_rejects_output_inside_reviewed_expectations(
    tmp_path: Path,
) -> None:
    fixtures_copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixtures_copy)
    expected_copy = fixtures_copy / "graphs" / "expected"

    with pytest.raises(ValueError, match="reviewed expected fixtures"):
        evaluate_fixture_corpus(
            ReviewedFixtureExtractor(),
            provider="local",
            fixtures_root=fixtures_copy,
            artifact_root=expected_copy,
        )
