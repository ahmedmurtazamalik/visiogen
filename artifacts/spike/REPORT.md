# M2 VSDX Template-Copying Spike

## Verdict: PARTIAL — Ubuntu validated, Microsoft Visio acceptance pending

The Ubuntu half of M2 is successful. Visiogen can copy all five template objects, relabel and reposition them, preserve the native container and callout structures, and create a copied dynamic connector whose page-level connection records and ShapeSheet formulas target the copied endpoints.

M2 remains partial until the exact generated artifact below passes the M2.3 checks in Microsoft Visio on Windows.

## Exact artifact identity

- Generator source commit: `152eeae9812f0b72539272161a7bfcb8affc7153`
- Canonical template source commit: `d2cf49446027d3b6130ff0d3793ace37e754fc58`
- Canonical template SHA-256: `646d9144b031224ba6211dc12193de48c424b3479ba44d14786b50a864484159`
- Generated artifact: `artifacts/spike/minimal.vsdx`
- Generated artifact SHA-256: `d5efe0490b1aeff6ffa26e00da60b80ab85a585b0ecb35be00f71d8017017846`
- Generated artifact size: `206488` bytes
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
- Generated callout targeting references the generated component, and its cached leader geometry ends on the component boundary.
- No serialized XML or relationship part contains generated `ns0`, `ns1`, or similar namespace prefixes.
- `python3 -m zipfile -t` completed successfully.
- Linux `file` identified the result as `Microsoft Visio 2013+`.
- LibreOffice headless converted the exact artifact to a one-page PDF successfully.
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

Both candidates are superseded and must not be used for final M2.3 acceptance.

## M2.3 Windows acceptance procedure

Using Microsoft Visio LTSC MSO Version 2409, Build 16.0.18014.20000, 64-bit:

1. Verify the downloaded file's SHA-256 is exactly `d5efe0490b1aeff6ffa26e00da60b80ab85a585b0ecb35be00f71d8017017846`.
2. Open `minimal.vsdx` in Microsoft Visio.
3. Confirm there is no repair, corruption, or unreadable-content prompt.
4. Confirm the five generated labels and objects are present and editable.
5. Move `Generated Process`; confirm the `feeds` connector endpoint follows it.
6. Move `Generated Component`; confirm the other endpoint follows it.
7. Confirm `Generated Subsystem` behaves as a native container.
8. Confirm callout `101` remains a native editable callout.
9. Save the file, close Visio, and reopen it.
10. Confirm there is still no repair prompt and the generated objects remain editable and glued.

If all ten checks pass, M2 can be marked validated. If Visio repairs the file or glue fails, M2 remains partial and the exact prompt and repaired file must be retained for diagnosis.
