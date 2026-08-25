"""Contract test for the frozen A0 evaluation matrix."""

import json
from pathlib import Path


CHARTER = Path(__file__).parents[1] / "fixtures" / "analysis" / "fixture_charter.json"
REQUIRED_VARIANTS = {"contradiction", "consistent", "ambiguous"}
REQUIRED_CATEGORIES = {
    "label",
    "reference_number",
    "object_existence",
    "relationship",
    "direction",
    "relationship_type",
    "containment",
    "sequence",
    "modality",
    "negation",
    "alias",
    "exhaustive_scope",
    "unreadable_evidence",
}


def test_a0_fixture_charter_covers_each_comparison_outcome() -> None:
    charter = json.loads(CHARTER.read_text())
    cases = {case["category"]: set(case["variants"]) for case in charter["consistency_cases"]}

    assert set(cases) == REQUIRED_CATEGORIES
    assert all(variants == REQUIRED_VARIANTS for variants in cases.values())
    assert len(charter["diagram_families"]) == 8
    assert "external_relationship" in charter["safety_cases"]
