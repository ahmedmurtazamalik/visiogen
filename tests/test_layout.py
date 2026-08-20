import pytest
from pydantic import ValidationError

from visiogen.layout import (
    LayoutError,
    LayoutResult,
    PageGeometry,
    apply_geometry,
    size_node,
)
from visiogen.models import DiagramGraph, DiagramNode


def one_node_graph(*, label: str = "Review request", reference: str | None = None) -> DiagramGraph:
    return DiagramGraph(
        title="One node",
        diagram_type="flowchart",
        orientation="top_to_bottom",
        nodes=[
            DiagramNode(
                id="review",
                type="process",
                label=label,
                reference_number=reference,
            )
        ],
    )


def test_apply_geometry_returns_new_layout_without_mutating_input() -> None:
    graph = one_node_graph()

    result = apply_geometry(
        graph,
        {"review": (2.0, 1.5, 2.625, 0.75)},
        PageGeometry(width=4.0, height=3.0),
    )

    positioned = result.graph.nodes[0]
    assert isinstance(result, LayoutResult)
    assert (positioned.x, positioned.y, positioned.width, positioned.height) == (
        2.0,
        1.5,
        2.625,
        0.75,
    )
    assert graph.has_geometry is False
    assert result.graph is not graph


@pytest.mark.parametrize(
    ("width", "height"),
    [(0.0, 3.0), (-1.0, 3.0), (4.0, 0.0), (4.0, -1.0)],
)
def test_page_geometry_requires_positive_dimensions(width: float, height: float) -> None:
    with pytest.raises(ValidationError):
        PageGeometry(width=width, height=height)


def test_apply_geometry_requires_exactly_one_box_per_node() -> None:
    graph = one_node_graph()

    with pytest.raises(LayoutError, match="missing geometry.*review"):
        apply_geometry(graph, {}, PageGeometry(width=4.0, height=3.0))

    with pytest.raises(LayoutError, match="unknown node.*other"):
        apply_geometry(
            graph,
            {
                "review": (2.0, 1.5, 2.625, 0.75),
                "other": (1.0, 1.0, 1.0, 1.0),
            },
            PageGeometry(width=4.0, height=3.0),
        )


@pytest.mark.parametrize(
    "box",
    [
        (2.0, 1.5, 0.0, 0.75),
        (2.0, 1.5, 2.625, -0.1),
        (0.0, 1.5, 2.625, 0.75),
        (2.0, -0.1, 2.625, 0.75),
    ],
)
def test_apply_geometry_requires_positive_center_and_size(
    box: tuple[float, float, float, float],
) -> None:
    with pytest.raises(LayoutError, match="positive geometry.*review"):
        apply_geometry(
            one_node_graph(),
            {"review": box},
            PageGeometry(width=4.0, height=3.0),
        )


def test_size_node_uses_visual_family_minimums() -> None:
    node = one_node_graph().nodes[0]

    size = size_node(node)

    assert size.width == 2.25
    assert size.height == 0.65
    assert size.wrapped_label == "Review request"


def test_size_node_wraps_long_labels_deterministically_with_bounded_dimensions() -> None:
    node = one_node_graph(
        label=(
            "Validate the submitted customer request against all required "
            "policy and authorization constraints before approval"
        )
    ).nodes[0]

    first = size_node(node)
    second = size_node(node)

    assert first == second
    assert "\n" in first.wrapped_label
    assert 2.25 <= first.width <= 5.0
    assert 0.65 < first.height <= 3.0
    assert max(map(len, first.wrapped_label.splitlines())) <= 36


def test_size_node_reserves_space_for_reference_number() -> None:
    without_reference = size_node(one_node_graph().nodes[0])
    with_reference = size_node(one_node_graph(reference="110").nodes[0])

    assert with_reference.height >= without_reference.height + 0.25


def test_apply_geometry_rejects_boxes_outside_page() -> None:
    with pytest.raises(LayoutError, match="outside page.*review"):
        apply_geometry(
            one_node_graph(),
            {"review": (3.5, 1.5, 2.0, 0.75)},
            PageGeometry(width=4.0, height=3.0),
        )
