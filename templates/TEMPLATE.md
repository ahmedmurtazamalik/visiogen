# Visio Template

## Template metadata

- File: `templates/template.vsdx`
- Palette page: `Template Palette`
- Format: Microsoft Visio Drawing (`.vsdx`)
- Purpose: M2 rendering and connector-glue feasibility spike
- Editing rule: only one person edits the binary template at a time

## Minimal palette

| Marker | Visio object | Intended use |
|---|---|---|
| `__template_process__` | Basic Flowchart process | Flowchart process nodes |
| `__template_component_rectangle__` | Basic rectangle | Generic system components |
| `__template_subsystem_container__` | Native Visio container | One-level subsystem grouping |
| `__template_reference_callout__` | Native Visio callout | Patent reference numerals |
| `__template_connector__` | Dynamic connector | Typed graph relationships |

Each marker occurs exactly once in the canonical package.

## Connector assumptions

The template connector is glued between the process and component shapes. Moving either endpoint shape in Microsoft Visio must preserve the connection.

The renderer spike uses the pinned `vsdx==0.6.1` package. Visiogen supplements its public APIs with tested XML-level handling for nested shape IDs, external ShapeSheet references, page-level connector records, and package namespace serialization.

## Authoring environment

- Product: Microsoft Visio LTSC MSO
- Version: 2409
- Build: 16.0.18014.20000
- Architecture: 64-bit
- Template source commit: `d2cf49446027d3b6130ff0d3793ace37e754fc58`

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
- Retargets the generated callout relationship and leader endpoint to the generated component.
- Copies both page-level connector records and retargets all connector ShapeSheet formulas to generated endpoint IDs.
- Serializes XML package parts with their declared default namespaces instead of ElementTree `ns0` prefixes.
- Refuses to overwrite the canonical template path.

Automated Ubuntu checks prove ZIP/package readability, unique shape IDs, exact generated labels, expected geometry, connector records, glue formulas, callout targeting, clean namespace serialization, and successful LibreOffice headless conversion. Microsoft Visio remains the authority for the M2.3 no-repair and movement tests.

## Editing rules

1. Preserve every marker exactly.
2. Keep marker values unique.
3. Never overwrite generated diagrams onto this file.
4. Do not add the complete production palette until M2 passes.
5. Validate every binary template revision by closing and reopening it in Microsoft Visio without a repair prompt.
6. Close Visio before staging changes so its temporary owner/lock file is removed.
