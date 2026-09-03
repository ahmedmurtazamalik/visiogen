# Generation v2 Native Renderer

**Status:** Implemented and structurally verified; Windows Visio acceptance pending

`render_ir` extends the existing template-based renderer to consume the immutable
G4 `RendererIR`. It reuses the canonical native masters, unique-ID cloning,
relationship retargeting, namespace-safe serialization, and atomic destination
replacement used by Generation v1.

## Coordinate and rendering contract

Construction-plan and IR coordinates use a top-left origin. The renderer performs
the single deterministic conversion to Visio's bottom-left page coordinates.
It does not move, resize, reroute, or restyle plan elements.

For each shape, the renderer applies the selected master, exact rectangle, text
box, typography, fill, line style, named connection points, and z-order. Native
container shapes retain their structure metadata; membership is represented by
reciprocal Visio `SheetRef` dependency formulas on both the container and each
member. Native auto-resize is disabled so Visio preserves the validated IR
geometry when opening the document. The requested padding is written to the
container margin cell and the header receives its explicit height.

Explicit straight, orthogonal, and polyline connectors receive local `MoveTo` and
`LineTo` geometry for every route point. Begin/end page cells are connected to the
requested named ports. Connector labels have an independent text pin, orientation,
offset, and opaque/transparent background. Jump behavior, line style, weight,
color, and arrowheads are applied directly.

`dynamic` is the only automatic-routing fallback. It is visible in the IR's
`connector_type` and uses the existing native Visio walk-glue formulas while its
connection rows still identify the requested ports.

Callouts use their exact carrier master, rectangle, text, target relationship, and
complete leader polyline. Page shape order is rebuilt from stable `(z_order,
plan_order)` keys after the template palette is removed.

## Verification boundary

Linux structural tests generate and reopen a package covering horizontal,
vertical, diagonal, branching, reciprocal, self-loop, nested-container, explicit
callout, and dynamic-fallback cases. They verify native connection rows, named
ports, route geometry, styles, membership formulas, z-order, template immutability,
and package validation.

Desktop Microsoft Visio remains authoritative for clean open, visual appearance,
editing, endpoint movement, save, close, and reopen. Run the generated candidate
through `scripts/validate_in_visio.ps1` with at least two connected shape labels.
G5 must remain open until that checksum-bound Windows report and manual review are
available.

The comprehensive topology fixture is a structural stress test, not a visual
acceptance candidate. Windows visual review must use the restrained
`g5-professional-acceptance-v6.vsdx` fixture containing one housing, three
components, two labeled routes, and two reference callouts. Its explicit geometry,
text, route, and style cells block inherited master formulas so desktop Visio does
not restore template defaults during recalculation. Group children scale with the
planned outer shape, and unused inherited geometry rows are explicitly deleted.
The container body is rendered on the group root so Visio cannot detach the
template's nested body subshape from its header during container recalculation.
The header is likewise reduced to one explicit rectangle so inherited decorative
geometry cannot draw outside the housing.

Windows move/undo review is mandatory, not optional visual polish. The restrained
candidate uses native movement-aware connector glue, target-relative callout leader
endpoints, and explicit deleted overrides for suppressed master children so opening,
moving, and undoing cannot resurrect cached master geometry.
