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
REQUIRED_UNSUPPORTED = {
    "pdf": {
        "encrypted",
        "portfolio_or_attachment",
        "javascript",
        "launch_action",
        "external_resource",
    },
    "docx": {
        "macro",
        "encrypted_member",
        "ole_or_embedded_package",
        "activex",
        "external_relationship",
        "unsafe_xml_declaration",
        "word_shapes_smartart_charts_textboxes",
    },
}


def test_a0_fixture_charter_covers_each_comparison_outcome() -> None:
    charter = json.loads(CHARTER.read_text())
    cases = {case["category"]: set(case["variants"]) for case in charter["consistency_cases"]}

    assert set(cases) == REQUIRED_CATEGORIES
    assert all(variants == REQUIRED_VARIANTS for variants in cases.values())
    assert len(charter["diagram_families"]) == 8
    assert "external_relationship" in charter["safety_cases"]


def test_a0_charter_freezes_unsupported_behavior_and_review_thresholds() -> None:
    charter = json.loads(CHARTER.read_text())

    assert {
        kind: set(constructs)
        for kind, constructs in charter["unsupported_constructs"].items()
    } == REQUIRED_UNSUPPORTED
    assert all(
        behavior in {
            "reject_typed_error",
            "extract_supported_content_and_warn_not_rendered",
        }
        for constructs in charter["unsupported_constructs"].values()
        for behavior in constructs.values()
    )
    rubric = charter["reviewer_rubric"]
    assert rubric["schema_reference_validity"] == 1
    assert rubric["contradiction_evidence_validity"] == 1
    assert rubric["clean_visible_label_accuracy_minimum"] >= 0.95
    assert rubric["clean_object_relationship_f1_minimum"] >= 0.90
    assert rubric["confirmed_contradiction_precision_minimum"] >= 0.90
    assert rubric["invented_visible_labels_or_references"] == 0
    assert rubric["forced_unclear_directions"] == 0
    assert rubric["non_exhaustive_omission_false_positives"] == 0
