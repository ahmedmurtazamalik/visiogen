# M2 VSDX Template-Copying Spike

## Verdict: PASS — Ubuntu structure and Microsoft Visio behavior validated

Visiogen copies all five template objects, relabels and repositions them, removes the source palette, preserves the native container and callout structures, and creates a dynamic connector whose page-level connection records and ShapeSheet formulas target the copied endpoints.

The exact artifact below passed Ubuntu package checks and authoritative Windows acceptance in Microsoft Visio.

## Exact artifact identity

- Generator source commit: `c47f844df7d933355f29876c423873480e867e8d`
- Canonical template source commit: `d2cf49446027d3b6130ff0d3793ace37e754fc58`
- Canonical template SHA-256: `646d9144b031224ba6211dc12193de48c424b3479ba44d14786b50a864484159`
- Generated artifact: `artifacts/spike/minimal.vsdx`
- Generated artifact SHA-256: `7b1453254f1390b7bc07e3bcd9d65226d11bf935de6ae547350da4c16076f4d2`
- Generated artifact size: `206534` bytes
- Renderer dependency: `vsdx==0.6.1`

The exact generated binary is committed at `artifacts/spike/minimal.vsdx` so the Windows validator receives the same bytes through `git pull`. Verify its checksum before testing.

## Reproduction command

```bash
uv run python3 -c "from visiogen.renderer import render_feasibility_spike; render_feasibility_spike('templates/template.vsdx', 'artifacts/spike/minimal.vsdx')"
```

ZIP timestamps mean a fresh run may produce different package bytes even when the XML content and behavior are equivalent. The checksum above identifies the exact Windows acceptance candidate.

## Ubuntu evidence

- Python package opened the canonical template and found every exact marker once.
- Generated labels each occur exactly once:
  - `Generated Process`
  - `Generated Component`
  - `Generated Subsystem`
  - `101`
  - `feeds`
- The generated page contains exactly five top-level objects.
- No `__template_*` marker or source palette object remains in the generated output.
- All page shape IDs are unique; no nested container IDs are duplicated.
- Generated process shape ID: `11`.
- Generated component shape ID: `12`.
- Generated connector shape ID: `19`.
- The connector has exactly two copied `<Connect>` rows:
  - `BeginX` from connector `19` to process `11`, `Connections.X2`.
  - `EndX` from connector `19` to component `12`, `Connections.X4`.
- `BeginX`, `BeginY`, and `BegTrigger` formulas reference `Sheet.11`.
- `EndX`, `EndY`, and `EndTrigger` formulas reference `Sheet.12`.
- Generated callout targeting references the generated component, its cached leader geometry ends on the component boundary, and its target formula depends dynamically on the component's `PinX`, `PinY`, and `Height` cells.
- No serialized XML or relationship part contains generated `ns0`, `ns1`, or similar namespace prefixes.
- `python3 -m zipfile -t` completed successfully.
- Linux `file` identified the result as `Microsoft Visio 2013+`.

- Full automated suite: `35 passed`.
- Total test coverage: `96%`; renderer coverage: `94%`.

## `vsdx==0.6.1` limitations handled by Visiogen

1. `Shape.copy()` does not assign fresh IDs to every nested container subshape. Visiogen recursively copies the complete tree and assigns unique IDs itself.
2. Copying a connector shape does not copy page-level `<Connect>` rows. Visiogen copies and retargets both rows.
3. Root ShapeSheet formulas that refer to external shapes are not remapped automatically. Visiogen retargets connector and callout formulas explicitly.
4. ElementTree's global namespace registry can serialize Visio parts with `ns0` prefixes. Visiogen serializes each package part with its root namespace declared as the default.
5. The library emits a debug print while recalculating connector geometry. Visiogen contains that output.

## Superseded Windows observation

- Candidate `5999fd15655481c5badd3f12522ddea83e22818b431a6abe47fd77018e937be3` opened without repair and contained all five generated objects, but incorrectly retained the source palette objects.
- Candidate `b13789bf6ceb0ec92924168d73eba75c2ac70b3aa51e6b1ed35b67ac0d9683de` passed the other reported Windows checks, but its callout leader stopped short of the generated component because moving the copied callout preserved stale cached leader geometry.
- Candidate `d5efe0490b1aeff6ffa26e00da60b80ab85a585b0ecb35be00f71d8017017846` opened cleanly and the callout visibly touched the component, but moving the component left the callout behind because the target-intersection formula was static.

All three candidates are superseded and must not be used for final M2.3 acceptance.

## M2.3 Windows acceptance

Validated with artifact SHA-256 `7b1453254f1390b7bc07e3bcd9d65226d11bf935de6ae547350da4c16076f4d2` in Microsoft Visio LTSC MSO Version 2409, Build 16.0.18014.20000, 64-bit:

- Opened without a repair, corruption, or unreadable-content prompt.
- Contained only the five generated editable objects and labels.
- Moving `Generated Process` kept the `feeds` connector attached.
- Moving `Generated Component` kept both `feeds` and callout `101` attached.
- The subsystem remained a native editable container.
- Callout `101` remained a native editable callout.
- Saving, closing, and reopening preserved the objects and attachments without a repair prompt.

M2 is accepted. The VSDX template-copying, connector-glue, and callout-association risks are sufficiently retired for M3.
