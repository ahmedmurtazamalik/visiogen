import pytest
from pydantic import ValidationError

from visiogen.extractor import ExtractedDiagramGraph
from visiogen.models import DiagramGraph


def extracted_payload() -> dict:
    return {
        "title": "Sensor system",
        "diagram_type": "system_block",
        "orientation": "left_to_right",
        "nodes": [
            {"id": "sensor", "type": "sensor", "label": "Sensor"},
            {"id": "controller", "type": "controller", "label": "Controller"},
        ],
        "edges": [
            {
                "source": "sensor",
                "target": "controller",
                "relation": "data",
                "direction": "forward",
            }
        ],
    }


def test_extraction_dto_converts_semantics_to_canonical_graph():
    extracted = ExtractedDiagramGraph.model_validate(extracted_payload())

    graph = extracted.to_diagram_graph()

    assert isinstance(graph, DiagramGraph)
    assert graph.nodes[0].type == "sensor"
    assert graph.edges[0].relation == "data"
    assert graph.has_geometry is False


def test_extraction_dto_rejects_geometry_fields():
    payload = extracted_payload()
    payload["nodes"][0]["x"] = 1.0

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExtractedDiagramGraph.model_validate(payload)


def test_extraction_dto_allows_missing_edge_id_for_normalization():
    extracted = ExtractedDiagramGraph.model_validate(extracted_payload())

    assert extracted.to_diagram_graph().edges[0].id is None
