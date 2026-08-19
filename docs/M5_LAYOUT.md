# M5 Acceptance — Deterministic Layout

**Status:** PASS
**Platform:** Ubuntu, Python 3.11, Graphviz 2.43.0
**Input contract:** geometry-free `visiogen.models.DiagramGraph`
**Output contract:** `visiogen.layout.LayoutResult`

## Scope completed

- Immutable page dimensions through `PageGeometry` and typed layout failures through `LayoutError`.
- A positioned deep copy of the canonical `DiagramGraph`; layout never mutates provider/reviewed input data.
- Deterministic visual-family sizing derived from `shape_mapper.py` defaults.
- Deterministic label wrapping, bounded long-label dimensions, and reserved reference-number height.
- A primary Graphviz strategy using stable DOT generation and `dot -Tplain`.
- A deterministic, dependency-light layered fallback with strongly connected component handling for cyclic graphs.
- One-level containment represented as Graphviz clusters and as final parent boxes enclosing all child geometry.
- Shared acceptance assertions for complete positive geometry, page bounds, ordinary-node non-overlap, container containment, input immutability, and byte-equivalent repeated output.

Extraction remains geometry-free. Both layout strategies consume the same canonical graph produced by extraction and normalization; neither provider adapter owns coordinates.

## Coordinate and sizing contract

All final values are inches and use center-based Visio coordinates:

```text
node.x, node.y       center position from the page's bottom-left origin
node.width, height   positive shape dimensions
page.width, height   positive final page dimensions
```

`dot -Tplain` emits bottom-left-origin coordinates in inches. Visiogen preserves that axis orientation and applies one deterministic translation to enforce page margins. It does not invert the y-axis in the renderer. Tests verify that top-to-bottom flows retain descending y coordinates (`start > review > finish`).

Graphviz's point-rounded width and height values are not allowed to alter canonical shape sizing. After parsing positions, Visiogen restores the exact deterministic dimensions calculated from semantic visual families.

## Primary Graphviz strategy

`GraphvizLayout`:

1. Emits stable DOT with nodes and edges sorted by canonical IDs.
2. Maps graph orientation to `rankdir=TB` or `rankdir=LR`.
3. Emits fixed deterministic node dimensions and wrapped labels.
4. Represents one-level containment with clusters.
5. Uses relation-specific weights while marking undirected associations as non-constraining.
6. Invokes an injectable subprocess boundary as `dot -Tplain`.
7. Parses and validates graph/node records, restores exact node sizes, derives container boxes, fits the final page, and returns a new positioned graph.

Clear `LayoutError` failures cover a missing executable, non-zero/timeout process failures, malformed plain output, missing child geometry, incomplete geometry, non-positive geometry, and boxes outside the final page.

The acceptance host resolved Graphviz as:

```text
/usr/bin/dot
dot - graphviz version 2.43.0 (0)
```

## Deterministic fallback strategy

`FallbackLayeredLayout` requires no external layout executable. It:

- Converts directed relations into stable graph constraints while excluding undirected associations.
- Honors reverse and bidirectional edge direction.
- Computes strongly connected components with sorted Tarjan traversal.
- Lays out the condensed acyclic graph in deterministic ranks.
- Uses stable node-ID tie-breaking and fixed node/rank spacing.
- Honors top-to-bottom and left-to-right orientation.
- Places isolated nodes without special cases.
- Keeps cycle members in one rank without overlapping their boxes.
- Derives parent container geometry after ordinary-node placement and fits every box inside the page.

The fallback is an explicit strategy, not a silent substitute for malformed Graphviz output.

## Acceptance corpus

Both strategies run against all nine reviewed canonical graphs:

1. `basic_system`
2. `bidirectional_architecture`
3. `eco_headphone`
4. `isolated_process`
5. `linear_flow`
6. `login_decision`
7. `method_loop`
8. `nested_subsystem`
9. `patent_schematic`

Both strategies also run against `tests/fixtures/layout/medium_system_25.json`, a 25-node, 45-edge, left-to-right system fixture with cross-layer links and a cycle.

This produces 20 shared layout acceptance combinations: 18 reviewed graph/strategy combinations plus two medium-system/strategy combinations.

## Offline acceptance evidence

```text
M5 implementation acceptance: 152 tests passed
Current complete suite after preferred-provider integration: 167 tests passed
96% total coverage
20/20 shared layout acceptance combinations passed
98% coverage: layout.py
98% coverage: layouts/fallback_layered.py
94% coverage: layouts/graphviz_layout.py
```

Additional evidence:

- Identical canonical input yields byte-equivalent `LayoutResult.model_dump_json()` output.
- Every positioned node has complete positive geometry.
- Every node box lies inside the final page.
- Ordinary node boxes do not overlap.
- Every child box lies strictly inside its parent container.
- Reviewed and medium input graphs remain byte-equivalent after layout.
- Both top-to-bottom and left-to-right directional checks pass.
- Real Graphviz execution, injected-runner behavior, malformed output, process failure, missing executable, cycles, isolated nodes, long labels, and reference-number sizing are covered.

## Dependency-ordered commits

```text
7a8772b Define deterministic layout geometry
6877ed6 Add deterministic Graphviz layout
7d16438 Add deterministic fallback layout
407e90d Add layout acceptance corpus
e561420 Add reviewed Graphviz DOT snapshots
```

M5 may feed M6 rendering integration. No Windows Visio acceptance is required for M5 itself because it produces deterministic canonical geometry only; native `.vsdx` interoperability remains independently authoritative on Windows for rendering milestones.
