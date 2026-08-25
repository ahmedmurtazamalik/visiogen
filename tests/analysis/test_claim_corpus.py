"""Integrity checks for the reviewed A5 claim corpus."""

import json
from pathlib import Path

from claim_fixture_builders import build_claim_case

_CORPUS = Path(__file__).parents[1] / "fixtures/analysis/claim_corpus.json"


def test_claim_corpus_covers_required_semantic_controls() -> None:
    corpus = json.loads(_CORPUS.read_text())
    cases = corpus["cases"]

    assert corpus["version"] == 1
    assert len(cases) == 7
    assert {item[3] for case in cases for item in case["expected"]} >= {
        "asserted", "required", "possible", "example", "negated"
    }
    assert sum(bool(case.get("unresolved_entity")) for case in cases) == 1
    assert sum(bool(case.get("require_exhaustive")) for case in cases) == 1
    for case in cases:
        selection, diagram = build_claim_case(case)
        assert selection.blocks[0].text == case["text"]
        assert diagram.objects
