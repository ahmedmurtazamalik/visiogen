from visiogen.design import DiagramDesign


def test_ai_connector_hints_survive_into_hybrid_layout_contract() -> None:
    design = DiagramDesign.model_validate(
        {
            "graph": {
                "title": "Flow",
                "diagram_type": "flowchart",
                "orientation": "left_to_right",
                "nodes": [
                    {"id": "source", "type": "process", "label": "Source"},
                    {"id": "target", "type": "process", "label": "Target"},
                ],
                "edges": [
                    {"id": "flow", "source": "source", "target": "target"}
                ],
            },
            "layout": {
                "composition": "compact_flow",
                "page_width": 8.0,
                "page_height": 4.0,
                "placements": [
                    {"node_id": "source", "x": 2.0, "y": 2.0, "width": 2.0, "height": 1.0},
                    {"node_id": "target", "x": 6.0, "y": 2.0, "width": 2.0, "height": 1.0},
                ],
                "connector_hints": [
                    {"edge_id": "flow", "source_side": "right", "target_side": "left"}
                ],
            },
            "rationale": "Direct flow.",
        }
    )

    layout = design.to_layout_result()

    assert layout.connector_hints == {"flow": ("right", "left")}
