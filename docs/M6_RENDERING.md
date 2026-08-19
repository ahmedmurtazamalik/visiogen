# M6 — Template-Based Renderer Integration

## Status

**Ubuntu implementation and structural acceptance: passed.**

**Microsoft Visio acceptance: pending.** M6 must not be called complete until the exact checksum-bound candidates below open without repair in Microsoft Visio, retain native connector and callout behavior after shapes move, and survive save/close/reopen.

No extraction provider is involved in M6. The renderer consumes an existing canonical `DiagramGraph` after deterministic M5 layout. Codex, local Qwen, and Gemini are not invoked.

## Contract

`render_layout(template_path, layout, output_path, *, automatic_reference_numbers=False)` consumes a `LayoutResult` and:

1. validates that output is not the canonical template or a same-file alias;
2. requires finite page dimensions;
3. requires finite node centers and strictly positive node dimensions;
4. loads every production marker exactly once;
5. copies containers before ordinary nodes;
6. maps canonical node and edge semantics through the immutable shape mapper;
7. assigns the exact M5 geometry instead of inventing coordinates;
8. preserves explicit `reference_number` values and only generates numbers when explicitly enabled;
9. keeps native reference callouts inside the page or rejects a page too small to contain one;
10. copies native connector shapes, labels and styles them, and retargets both page-level `<Connect>` rows and all six endpoint formulas to generated shape IDs;
11. removes the source palette and obsolete source connection rows before saving; and
12. saves through the namespace-safe serializer without third-party debug output.

Missing geometry, non-finite geometry, non-positive dimensions, missing edge endpoints, impossible callout bounds, duplicate/missing template markers, and canonical-template aliases fail explicitly.

## RED → GREEN slices

M6 was implemented in dependency order:

1. production marker inventory, container-first node copying, exact geometry, and missing-geometry rejection;
2. explicit native reference callouts, opt-in automatic numbering, dynamic target formulas, and page clamping;
3. styled and labeled native connectors with generated endpoint IDs, page connection rows, and ShapeSheet endpoint formulas;
4. three-package fixture acceptance; and
5. reviewer-driven hardening for hard-link template aliases, invalid geometry, undersized callout pages, and renderer stdout.

The independent review that discovered the three renderer defects was treated as a failed gate. Each defect received a reproducing test before its correction. A fresh independent review of the corrected snapshot is required before push.

## Representative fixture acceptance

The smoke corpus covers:

- `linear_flow.json` — flowchart nodes and directed native connectors;
- `basic_system.json` — typed system nodes and bidirectional native connectivity; and
- `renderer/headphone.json` — housing/container semantics, explicit references, typed links, labels, callouts, and connectors.

For every generated package, automated checks require:

- ZIP integrity and parsing of every XML/relationship part;
- no generated `ns0`/`ns1` namespace prefixes;
- unique top-level and nested Visio shape IDs;
- expected top-level output count;
- no surviving `__template_*` labels;
- expected node and reference labels;
- exactly two page-level connection rows per connector;
- `BeginX`, `BeginY`, and `BegTrigger` formulas targeting the generated source;
- `EndX`, `EndY`, and `EndTrigger` formulas targeting the generated target;
- exact M5 page dimensions; and
- unchanged canonical-template checksum.

## Ubuntu evidence

Corrected renderer snapshot:

```text
3c55f297506c6c0c842862e9f60fb7addc449994
```

Full suite and coverage:

```text
185 passed in 44.19s
97% total coverage
96% renderer coverage
```

Build:

```text
Successfully built dist/visiogen-0.1.0.tar.gz
Successfully built dist/visiogen-0.1.0-py3-none-any.whl
```

All three exact Windows candidates passed the structural package audit. LibreOffice Draw also imported and exported all three to PDF; that is only a secondary compatibility smoke test and is not Microsoft Visio acceptance.

Canonical template:

```text
path: templates/template.vsdx
sha256: db5637b9ac65e5733c4b54d83b0f08bc3d06649bebea5a4856eb3089e459dd10
```

## Checksum-bound Windows candidates

Directory:

```text
artifacts/m6-windows-acceptance/
```

Candidate package:

```text
visiogen-m6-windows-acceptance.zip
9e35cf3b9d5d9d51e9de1609d50b78fc99412194607d3ceade747132338e5d71
```

Documents:

```text
linear_flow.vsdx
bytes: 410207
sha256: a804798f58aa96276d17d433a9f61674699a61c010e656af1530c8651b57a819

basic_system.vsdx
bytes: 412027
sha256: 2966eeb22e6a8682caf5b760d0088e033e976b76f9e4bef47d0bf3a1ba882203

headphone.vsdx
bytes: 449986
sha256: e44f370ac460be1706d163ed304d9123875e5eb785d07636f37333a264df6e5c
```

`manifest.json` binds these files to the corrected source commit and canonical-template checksum.

## Authoritative Microsoft Visio gate

On Windows with Microsoft Visio:

1. verify each document SHA-256 before opening;
2. open each document and fail the gate if Visio reports repair, recovery, unreadable content, or conversion;
3. verify every node, connector, container, label, and reference callout is individually selectable and editable;
4. move both endpoints of every connector and verify both ends remain glued;
5. move every target with a reference callout and verify the leader remains attached;
6. verify directed and bidirectional arrowheads and line styles remain correct;
7. save each document under a new filename, close Visio, reopen the saved copy, and repeat the attachment checks; and
8. report the exact candidate checksum, Visio version, and pass/fail result for each document.

Until that procedure passes, the honest milestone state is **M6 implemented and Ubuntu-verified, Windows acceptance pending**.
