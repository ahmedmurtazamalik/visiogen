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

The exact Python `vsdx` package version and APIs remain unconfirmed until the Ubuntu M2 spike succeeds.

## Authoring environment

- Product: Microsoft Visio LTSC MSO
- Version: 2409
- Build: 16.0.18014.20000
- Architecture: 64-bit
- Template source commit: `d2cf49446027d3b6130ff0d3793ace37e754fc58`

Product IDs and session IDs are deliberately not recorded because they are unnecessary for compatibility testing.

## Editing rules

1. Preserve every marker exactly.
2. Keep marker values unique.
3. Never overwrite generated diagrams onto this file.
4. Do not add the complete production palette until M2 passes.
5. Validate every binary template revision by closing and reopening it in Microsoft Visio without a repair prompt.
6. Close Visio before staging changes so its temporary owner/lock file is removed.
