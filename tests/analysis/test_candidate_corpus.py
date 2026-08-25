"""Integrity checks for the reviewed, locally generated A2 corpus."""

import json
from pathlib import Path

from PIL import Image

from candidate_fixture_builders import write_candidate_fixture

_MANIFEST = Path(__file__).parents[1] / "fixtures/analysis/candidate_corpus.json"


def test_candidate_corpus_is_balanced_reviewed_and_reproducible(tmp_path: Path) -> None:
    corpus = json.loads(_MANIFEST.read_text())
    cases = corpus["cases"]
    assert corpus["version"] == 1
    assert "Locally generated" in corpus["provenance"]
    assert len({case["id"] for case in cases}) == len(cases)
    labels = [case["expected_label"] for case in cases]
    assert labels.count("diagram") >= 3
    assert labels.count("non_diagram") >= 3
    assert labels.count("unknown") >= 1
    assert all(case["rationale"] for case in cases)

    for case in cases:
        first = write_candidate_fixture(
            tmp_path / f"first-{case['id']}.png",
            case["generation_kind"],
        )
        second = write_candidate_fixture(
            tmp_path / f"second-{case['id']}.png",
            case["generation_kind"],
        )
        assert first.read_bytes() == second.read_bytes()
        with Image.open(first) as image:
            assert image.size == (640, 480)
