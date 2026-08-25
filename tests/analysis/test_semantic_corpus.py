"""Integrity checks for the locally generated A3 semantic corpus."""

import json
from pathlib import Path

from PIL import Image

from semantic_fixture_builders import write_semantic_fixture

_MANIFEST = Path(__file__).parents[1] / "fixtures/analysis/semantic_corpus.json"


def test_semantic_corpus_is_complete_balanced_and_reproducible(tmp_path: Path) -> None:
    corpus = json.loads(_MANIFEST.read_text())
    cases = corpus["cases"]
    assert corpus["version"] == 1
    assert "Locally generated" in corpus["provenance"]
    assert {case["generation_kind"] for case in cases} == {
        "branching_flow",
        "contained_system",
        "reference_schematic",
        "crossing_without_junction",
        "dense_tiled",
        "ambiguous_arrow",
    }
    assert sum(case["ambiguous_direction"] for case in cases) == 1
    assert all(case["objects"] for case in cases)
    assert all(case["relationships"] for case in cases)

    for case in cases:
        first = write_semantic_fixture(
            tmp_path / f"first-{case['id']}.png",
            case["generation_kind"],
        )
        second = write_semantic_fixture(
            tmp_path / f"second-{case['id']}.png",
            case["generation_kind"],
        )
        assert first.read_bytes() == second.read_bytes()
        with Image.open(first) as image:
            assert image.width >= 1000
            assert image.height >= 700
