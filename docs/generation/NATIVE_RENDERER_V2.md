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
box, typography, fill, line style, named connection points, and z-order. Before
resizing it removes inherited-only Geometry, Scratch, Control, and User caches
copied from the template palette, so native master formulas evaluate at the new
instance dimensions instead of drawing the palette's old outline. Named ports use
Width/Height-relative formulas and remain on the visible edge after a user resize.
Native container shapes retain their structure metadata; membership is represented by
reciprocal Visio `SheetRef` dependency formulas on both the container and each
member. Native auto-resize is disabled so Visio preserves the validated IR
geometry when opening the document. The requested padding is written to the
container margin cell, the header receives its explicit height and contrasting
fill, and suppressed master-child subtrees are recursively hidden.

Explicit straight, orthogonal, and polyline connectors receive local `MoveTo` and
`LineTo` geometry for every route point. Begin/end page cells are connected to the
requested named ports with live `PAR(PNT(Sheet...!Connections...))` formulas, not
cached page coordinates. Their first and last geometry rows follow those live
endpoints. Generated inward port vectors match Visio's Type-0 connection-point
semantics, and each native `Connect.ToPart` is calculated from the effective row
index after inherited master rows. This keeps `ToCell` and `ToPart` consistent when
Visio recalculates the page.

Straight and orthogonal routes use `ConFixedCode=0`, allowing desktop Visio to
recalculate the route after an endpoint moves instead of preserving an obsolete
page-coordinate bend that can reverse the arrow's final leg. They write the
connector-local `ShapeRouteStyle` cell (`2` for straight and `1` for orthogonal),
never the page-only `RouteStyle` cell; straight routes also use
`ConLineRouteExt=1`. Explicitly requested freeform polylines use
`ConFixedCode=2` to retain their authored bends. Connector labels have an
independent text pin, orientation, offset, and opaque/transparent background. Jump
behavior, line style, weight, color, and arrowheads are applied directly.

`dynamic` is the only automatic-routing fallback. It is visible in the IR's
`connector_type` and uses the existing native Visio walk-glue formulas with
whole-shape `PinX` connection rows, allowing Visio to choose perimeter attachments.

Callouts use their exact carrier master, rectangle, text, target relationship, and
complete leader polyline. Page shape order is rebuilt from stable `(z_order,
plan_order)` keys after the template palette is removed.

## Verification boundary

Linux structural tests generate and reopen a package covering horizontal,
vertical, diagonal, branching, reciprocal, self-loop, nested-container, explicit
callout, and dynamic-fallback cases. They verify native connection rows, named
ports, effective `ToPart` indexes, inward vectors, route geometry and routing cells,
resize-relative port formulas, absence of stale palette geometry caches, recursively
hidden container children, styles, membership formulas, z-order, template
immutability, and package validation.

Desktop Microsoft Visio remains authoritative for clean open, visual appearance,
editing, endpoint movement, save, close, and reopen. Run the generated candidate
through `scripts/validate_in_visio.ps1` with at least two connected shape labels.
G5 must remain open until that checksum-bound Windows report and manual review are
available.

The comprehensive topology fixture is a structural stress test, not a visual
acceptance candidate. Windows visual review must use the restrained
`g5-professional-acceptance-v7.vsdx` fixture containing one housing, three
components, two labeled routes, and two reference callouts. Its explicit geometry,
text, route, and style cells block inherited master formulas so desktop Visio does
not restore template defaults during recalculation. Group children scale with the
planned outer shape, and unused inherited geometry rows are explicitly deleted.
The container body is rendered on the group root so Visio cannot detach the
template's nested body subshape from its header during container recalculation.
The header is likewise reduced to one explicit rectangle so inherited decorative
geometry cannot draw outside the housing.

Windows move/undo review is mandatory, not optional visual polish. The acceptance
automation rejects `ToPart`/`ToCell.Row` disagreement, frozen native-routed connectors,
and stale drawing extents for the bounded masters exercised by the acceptance
corpus. Static endpoint coordinates must match their named connection points. It
also checks the geometry bounds of every straight connector and the approach
direction of every orthogonal terminal leg before movement, after movement, after
undo/redo, and after save/reopen. The corpus requires at least one endpoint to
cross its old terminal bend. These checks catch stale palette outlines, reversed
arrow legs, and loop-back detours even when endpoint cells still move.
Master-specific silhouette projection is covered structurally for nonrectangular
ports. The restrained candidate also uses target-relative callout leader endpoints
and explicit deleted overrides for suppressed master children so opening, moving,
and undoing cannot resurrect cached master geometry.

Generated instances also use explicit, unguarded numeric formulas for every local
shape transform (`PinX`, `PinY`, `Width`, `Height`, `LocPinX`, and `LocPinY`). This
is deliberate: a blocked `No Formula` instance transform can be replaced by master
inheritance during Visio undo, restoring the master's shared default pin near the
lower-left of the page. Numeric local formulas remain normally editable while
giving undo an instance-specific value to restore. Dynamic connector transform
formulas remain movement-aware and guarded.
