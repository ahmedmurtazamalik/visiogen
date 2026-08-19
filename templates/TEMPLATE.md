# Visio Template

## Template metadata

- File: `templates/template.vsdx`
- Palette page: `Template Palette`
- Format: Microsoft Visio Drawing (`.vsdx`)
- Current purpose: M3 canonical production palette for template-based rendering
- Page size: 22 × 17 inches, landscape
- Current template SHA-256: `db5637b9ac65e5733c4b54d83b0f08bc3d06649bebea5a4856eb3089e459dd10`
- M3 expansion source commit: `7b11841ac9550d25f6338a3a1b26a479708720dd`
- Editing rule: only one person edits the binary template at a time

## Production palette inventory

Status key: **U✓** = Ubuntu ZIP/XML and `vsdx` structural validation passed; **W?** = expanded-template Windows close/reopen smoke confirmation pending.

| Marker | Semantic users | Default size (in) | Container-capable | Status |
|---|---|---:|:---:|:---:|
| `__template_terminator__` | `terminator` | 2.6 × 0.9 | No | U✓ / W? |
| `__template_process__` | `process` | 2.625 × 0.75 | No | U✓ / W? |
| `__template_decision__` | `decision` | 2.3 × 1.5 | No | U✓ / W? |
| `__template_input_output__` | `input_output` | 3.0 × 1.1 | No | U✓ / W? |
| `__template_database__` | `data_store`, `memory`, `database` | 2.5 × 1.35 | No | U✓ / W? |
| `__template_document__` | `document` | 2.7 × 1.15 | No | U✓ / W? |
| `__template_predefined_process__` | `predefined_process` | 3.0 × 1.0 | No | U✓ / W? |
| `__template_delay__` | `delay` | 2.5 × 1.1 | No | U✓ / W? |
| `__template_note__` | `note` | 2.7 × 1.2 | No | U✓ / W? |
| `__template_connector_hub__` | `connector_hub` | 1.35 × 1.35 | No | U✓ / W? |
| `__template_component_rectangle__` | `component`, `actuator`, `communication_module` | 3.75 × 1.0 | No | U✓ / W? |
| `__template_subsystem_container__` | `subsystem` | 5.5 × 2.8 | Yes | U✓ / W? |
| `__template_controller__` | `controller`, `processor` | 3.0 × 1.1 | No | U✓ / W? |
| `__template_sensor__` | `sensor`, `transducer` | 1.8 × 1.8 | No | U✓ / W? |
| `__template_power_source__` | `power_source` | 2.9 × 1.4 | No | U✓ / W? |
| `__template_interface__` | `interface` | 3.0 × 0.5625 | No | U✓ / W? |
| `__template_external_system__` | `external_system`, `service` | 3.2 × 1.25 | No | U✓ / W? |
| `__template_housing_container__` | `housing` | 6.5 × 3.0 | Yes | U✓ / W? |
| `__template_reference_callout__` | Node reference numerals | 2.625 × 0.3125 | No | U✓ / W? |
| `__template_connector__` | All `RelationType` values | Dynamic | No | U✓ / W? |

Each marker occurs exactly once in the canonical package. The page contains exactly 20 top-level palette objects. Semantic aliases deliberately reuse the listed visual templates rather than multiplying visually redundant masters.

## Connector assumptions

The template connector is glued between the process and component shapes. Moving either endpoint shape in Microsoft Visio must preserve the connection.

The renderer spike uses the pinned `vsdx==0.6.1` package. Visiogen supplements its public APIs with tested XML-level handling for nested shape IDs, external ShapeSheet references, page-level connector records, and package namespace serialization.

## Authoring environment

- Product: Microsoft Visio LTSC MSO
- Version: 2409
- Build: 16.0.18014.20000
- Architecture: 64-bit
- M2 minimal template source commit: `d2cf49446027d3b6130ff0d3793ace37e754fc58`

Product IDs and session IDs are deliberately not recorded because they are unnecessary for compatibility testing.

## M2.1 Windows acceptance

Validated in Microsoft Visio LTSC MSO Version 2409, Build 16.0.18014.20000, 64-bit:

- Closed and reopened `template.vsdx` without a repair or corruption prompt.
- All palette objects and marker text were preserved after reopening.
- Moving the process shape kept its connector endpoint attached.
- Moving the component rectangle kept its connector endpoint attached.
- The dynamic connector rerouted while remaining glued at both ends.

M2.1 is accepted. M2.2 must separately prove that Python-generated copies retain these properties.

## M2.2 Ubuntu structural acceptance

The Ubuntu feasibility renderer:

- Loads all five markers by exact text and rejects missing or duplicate markers.
- Copies the complete top-level object for each marker, including the native container group.
- Assigns unique IDs recursively to nested copied shapes.
- Relabels and repositions each copied object without mutating the canonical template.
- Removes the source palette objects and their connection records from the generated output.
- Retargets the generated callout relationship and uses a dynamic ShapeSheet formula so its leader endpoint follows the generated component.
- Copies both page-level connector records and retargets all connector ShapeSheet formulas to generated endpoint IDs.
- Serializes XML package parts with their declared default namespaces instead of ElementTree `ns0` prefixes.
- Refuses to overwrite the canonical template path.

Automated Ubuntu checks prove ZIP/package readability, unique shape IDs, exact generated labels, expected geometry, connector records, glue formulas, callout targeting, clean namespace serialization, and successful LibreOffice headless conversion. Microsoft Visio remains the authority for the M2.3 no-repair and movement tests.

## M2.3 Windows acceptance

The exact accepted generated artifact is:

- Generator source commit: `c47f844df7d933355f29876c423873480e867e8d`.
- Artifact publication commit: `beee9b404bca15e47828815f8619293a0912ce6a`.
- Artifact SHA-256: `7b1453254f1390b7bc07e3bcd9d65226d11bf935de6ae547350da4c16076f4d2`.

Validated in Microsoft Visio LTSC MSO Version 2409, Build 16.0.18014.20000, 64-bit:

- Opened without a repair, corruption, or unreadable-content prompt.
- Only the five generated editable objects and labels remained in the output.
- Moving either endpoint shape kept `feeds` attached.
- Moving `Generated Component` kept callout `101` attached.
- The subsystem container and reference callout remained native editable Visio objects.
- Save, close, and reopen completed without repair and preserved the attachments.

M2 is fully accepted against these exact artifact bytes.

## M3.1 expanded-palette structural acceptance

The M3 template expansion is committed at `7b11841ac9550d25f6338a3a1b26a479708720dd` with SHA-256 `db5637b9ac65e5733c4b54d83b0f08bc3d06649bebea5a4856eb3089e459dd10`.

Ubuntu validation confirms:

- The `Template Palette` page is exactly 22 × 17 inches.
- Every one of the 20 production markers occurs exactly once.
- The page contains exactly 20 top-level palette objects.
- All 29 top-level and nested shape IDs are unique.
- Both native container groups remain complete and empty of ordinary palette nodes.
- The accepted process-to-component Dynamic Connector retains both page-level connection records and endpoint ShapeSheet formulas.
- The reference callout relationship still targets the component.
- ZIP/package integrity passes and LibreOffice converts the template to a one-page PDF.
- The complete automated suite passes with 36 tests.

The expanded template's Windows close/reopen, connector-movement, callout-movement, and native-container smoke confirmation remains required before M3.2 mapper implementation begins.

## Editing rules

1. Preserve every marker exactly.
2. Keep marker values unique.
3. Never overwrite generated diagrams onto this file.
4. Expand the palette only with real Visio objects and preserve the accepted connector, container, and callout semantics.
5. Validate every binary template revision by closing and reopening it in Microsoft Visio without a repair prompt.
6. Close Visio before staging changes so its temporary owner/lock file is removed.
