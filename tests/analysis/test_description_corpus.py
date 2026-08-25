"""A4 coverage over every exact semantic result accepted by A3."""

import json
from pathlib import Path

from visiogen.analysis.description import (
    compose_diagram_description,
    render_description_markdown,
)
from visiogen.analysis.description_evaluation import score_description_coverage
from visiogen.analysis.semantics import AnalyzedDiagram

_REPORT = Path(__file__).parents[2] / "docs/acceptance/evidence/a3-semantic-reconstruction.json"


def test_descriptions_cover_all_accepted_a3_semantics_deterministically() -> None:
    report = json.loads(_REPORT.read_text())
    assert report["status"] == "passed"
    assert len(report["cases"]) == 6

    for case in report["cases"]:
        diagram = AnalyzedDiagram.model_validate(case["result"]["reconstruction"]["diagram"])
        first = compose_diagram_description(diagram)
        second = compose_diagram_description(diagram)
        score = score_description_coverage(first, diagram)

        assert first == second
        assert render_description_markdown(first) == render_description_markdown(second)
        assert score.object_coverage == 1
        assert score.relationship_coverage == 1
        assert score.group_coverage == 1
        assert score.annotation_coverage == 1
        assert score.legend_coverage == 1
        assert score.limitation_coverage == 1
        assert score.visible_label_coverage == 1
        assert score.reference_number_coverage == 1
        assert score.ambiguity_coverage == 1
        assert score.canonical_sections
