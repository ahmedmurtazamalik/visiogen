"""Build strict A5 inputs from the reviewed claim corpus."""

from visiogen.analysis.claims import SelectedTextBlock, TextSelection
from visiogen.analysis.semantics import AnalyzedDiagram
from visiogen.documents.models import SourceLocation


def build_claim_case(case: dict) -> tuple[TextSelection, AnalyzedDiagram]:
    text = case["text"]
    selection = TextSelection(
        source_id=f"claim-corpus:{case['id']}",
        candidate_id="candidate-0001",
        blocks=[
            SelectedTextBlock(
                block_id="text-0001",
                text=text,
                origin="native",
                order=0,
                location=SourceLocation(block_id="text-0001", paragraph_index=0),
                reasons=["explicit"],
            )
        ],
        max_blocks=4,
        max_characters=4000,
        selected_characters=len(text),
    )
    objects = []
    for index, (label, reference) in enumerate(case["objects"], start=1):
        left = 0.05 + (index - 1) * 0.3
        objects.append(
            {
                "id": f"object-{index:04d}",
                "visible_label": label,
                "normalized_label": label.casefold(),
                "semantic_type": "component",
                "visual_shape": "rectangle",
                "reference_numbers": [reference] if reference else [],
                "bbox": {"left": left, "top": 0.2, "right": left + 0.2, "bottom": 0.4},
                "evidence_ids": [f"evidence-{index:04d}"],
                "confidence": "high",
            }
        )
    diagram = AnalyzedDiagram.model_validate(
        {
            "candidate_id": "candidate-0001",
            "family": "system_block",
            "orientation": "left_to_right",
            "objects": objects,
            "relationships": [],
            "confidence": "high",
        }
    )
    return selection, diagram
