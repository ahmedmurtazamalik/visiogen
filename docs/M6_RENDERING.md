# M6 — Template-Based Renderer Integration

## Status

**Ubuntu implementation and structural acceptance: passed.**

**Microsoft Visio acceptance: failed for the original candidate; corrective R2 acceptance is pending.** The original files opened and their ordinary connectors were mostly correct, but the headphone callout leaders did not follow moved targets and the generated geometry was too large and cramped. M6 must not be called complete until the corrective R2 candidates pass move/save/close/reopen testing in Microsoft Visio.

No extraction provider is involved in M6. The renderer consumes an existing canonical `DiagramGraph` after deterministic M5 layout. Codex, local Qwen, and Gemini are not invoked.

## Contract

`render_layout(template_path, layout, output_path, *, automatic_reference_numbers=False)` consumes a `LayoutResult` and:

1. validates that output is not the canonical template or a same-file alias, writes to a private sibling, and atomically replaces the destination;
2. requires finite page dimensions;
3. requires finite node centers, strictly positive node dimensions, and complete node bounds inside the declared page;
4. loads every production marker exactly once;
5. copies containers before ordinary nodes;
6. maps canonical node and edge semantics through the immutable shape mapper;
7. assigns the exact M5 geometry instead of inventing coordinates;
8. preserves explicit `reference_number` values and only generates collision-free numbers when explicitly enabled;
9. places compact reference numeral carriers on a non-obstructing side of their targets, keeps native callouts inside the page, or rejects impossible placement;
10. copies native connector shapes, labels and styles them, and retargets both page-level `<Connect>` rows and all six endpoint formulas to generated shape IDs;
11. removes the source palette and obsolete source connection rows before saving; and
12. saves through the namespace-safe serializer without third-party debug output, a `vsdx` module monkey patch, or a persistent ElementTree namespace-registry mutation.

Missing geometry, non-finite geometry, non-positive dimensions, missing edge endpoints, impossible callout bounds, duplicate/missing template markers, and canonical-template aliases fail explicitly.

## RED → GREEN slices

M6 was implemented in dependency order:

1. production marker inventory, container-first node copying, exact geometry, and missing-geometry rejection;
2. explicit native reference callouts, opt-in automatic numbering, dynamic target formulas, and collision-aware numeral placement;
3. styled and labeled native connectors with generated endpoint IDs, page connection rows, and ShapeSheet endpoint formulas;
4. three-package fixture acceptance; and
5. reviewer-driven hardening for hard-link aliases and races, atomic writes, invalid/out-of-page geometry, undersized callout pages, non-obstructing reference carriers, collision-free automatic references, omitted style defaults, serializer global-state isolation, and renderer stdout.

Every independent review that found a reproducible local defect was treated as a failed gate. Each valid defect received a reproducing test before correction. The final fresh independent review of exact renderer snapshot `021d018421034f13919e4ebc0e7f6746d69983ca` passed with no security concerns, logic errors, or locally satisfiable requirements gaps. Microsoft Visio acceptance remains the external gate.

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
- every rendered node's exact M5 `x`, `y`, `width`, and `height`;
- exactly two page-level connection rows per connector;
- each connector bound to its intended semantic source and target;
- `BeginX`, `BeginY`, and `BegTrigger` formulas targeting the generated source;
- `EndX`, `EndY`, and `EndTrigger` formulas targeting the generated target;
- mapped arrowheads, line pattern, line weight, and line color;
- every callout targeting its intended generated node, staying inside page bounds, and keeping its transformed text carrier clear of the target;
- exact M5 page dimensions; and
- unchanged canonical-template checksum.

## Corrective R2 after real Visio feedback

The first authoritative Windows check superseded the original candidate after finding two user-visible defects:

1. headphone callout numerals and leaders stayed fixed when their target components moved; and
2. nodes were oversized relative to the page, spacing was cramped, connectors looked unnecessarily tangled, and the half-inch page margin left too little whitespace.

The corrective implementation is split into two commits:

```text
e9f47b8 Keep reference callout leaders dynamically attached
0b28b85 Improve generated diagram spacing and scale
```

The callout correction writes explicit local formulas through the complete visible dependency chain: `User.msvSDTargetIntersection` dynamically references the generated target, `User.LeaderEnd` explicitly references that target-intersection cell, and both visible leader endpoint cells explicitly reference `User.LeaderEnd`. The geometry correction reduces ordinary node defaults, increases node spacing from `0.75 in` to `1.25 in`, increases rank spacing from `1.00 in` to `1.50 in`, and increases the page margin from `0.50 in` to `1.00 in` on every side.

Compared with the original layout implementation, representative page area changed by +50.9% for the linear flow, +29.5% for the basic system, and +10.0% for the headphone fixture, while mean ordinary-node area decreased by 28.4%, 32.9%, and 28.9% respectively. The full suite passes with `197 passed`.

Corrective bundle:

```text
artifacts/m6-windows-acceptance-r2/visiogen-m6-windows-acceptance-r2.zip
sha256: b143367a39285334a35a1b374c1d6fd928786c91905c929fdbe4475821c857ba
```

Its structural audit confirms ZIP/XML integrity, unique shape IDs, one-inch node margins, zero reference-carrier overlap, dynamic target formulas for all six headphone callouts, explicit local `User.LeaderEnd` formulas, and explicit visible leader endpoint formulas. LibreOffice imported all three candidates and generated PNG previews. These checks do not replace the pending real-Visio movement test.

## Original Ubuntu evidence

Corrected renderer snapshot:

```text
021d018421034f13919e4ebc0e7f6746d69983ca
```

Full suite and coverage:

```text
197 passed in 63.32s
96% total coverage
95% renderer coverage
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

## Superseded original Windows candidates

Directory:

```text
artifacts/m6-windows-acceptance/
```

Candidate package:

```text
visiogen-m6-windows-acceptance.zip
a8c189701baa47eeabbeddd463cffd884de99c9dd212c7a0dd31cedb93230ac0
```

Documents:

```text
linear_flow.vsdx
bytes: 410195
sha256: a69db2c5a0b095e6b0d919be6dccc3b037ee519cd5954fc668c7b93a58866cd4

basic_system.vsdx
bytes: 412125
sha256: 82a554bb038b21a1baf7d15c11097505876ebb206d70e0745183aef38375c2cd

headphone.vsdx
bytes: 449742
sha256: 0b0c56af31ba5b32ee477e159b03eec043ab5116adee106bff24895bbe2cd6a5
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

Until the corrective R2 procedure passes, the honest milestone state is **M6 corrected and Ubuntu-verified, corrective Windows acceptance pending**.
