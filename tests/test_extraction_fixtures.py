import json
from pathlib import Path

from visiogen.models import DiagramGraph
from visiogen.normalization import normalize_graph


FIXTURES = Path(__file__).parent / "fixtures"
TEXT_DIR = FIXTURES / "text"
EXPECTED_DIR = FIXTURES / "graphs" / "expected"
CASES = {
    "linear_flow": "graph",
    "login_decision": "graph",
    "method_loop": "graph",
    "isolated_process": "graph",
    "ambiguous_no_diagram": "error",
    "basic_system": "graph",
    "bidirectional_architecture": "graph",
    "nested_subsystem": "graph",
    "eco_headphone": "graph",
    "patent_schematic": "graph",
}


def test_reviewed_extraction_fixture_corpus_is_complete() -> None:
    assert {path.stem for path in TEXT_DIR.glob("*.txt")} == set(CASES)
    assert {path.name.removesuffix(".json") for path in EXPECTED_DIR.glob("*.json")} == {
        f"{name}.error" if kind == "error" else name for name, kind in CASES.items()
    }


def test_reviewed_graph_fixtures_are_canonical_and_geometry_free() -> None:
    for name, kind in CASES.items():
        prompt = (TEXT_DIR / f"{name}.txt").read_text().strip()
        assert prompt
        if kind == "error":
            expected = json.loads((EXPECTED_DIR / f"{name}.error.json").read_text())
            assert expected["expected_error"] == "NoDiagramContentError"
            continue

        graph = DiagramGraph.model_validate_json((EXPECTED_DIR / f"{name}.json").read_text())
        assert graph.has_geometry is False
        assert normalize_graph(graph) == graph
