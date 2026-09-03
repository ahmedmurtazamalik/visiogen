# Generation v2 Compiler IR

Generation v2 compiles a validated `VisioConstructionPlan` into a strict,
renderer-neutral `RendererIR` before any VSDX package is opened or mutated. The
compiler preserves the planner's visual decisions and resolves only mechanical
facts required by a native renderer.

## Resolved contract

The immutable IR contains:

- canonical native master marker and master name pairs;
- exact visible shape text and connector endpoint/port ownership;
- normalized color tokens and strict typography, shape, and connector styles;
- absolute named-port coordinates;
- connector routes including resolved source and target endpoints;
- connector-label anchors, callouts, leader routes, and explicit shape/callout
  z-order; and
- page, region, guide, containment, and clipping data.

Connectors do not carry z-order in the version 1 construction-plan schema. The
compiler therefore applies the documented mechanical rule that connectors follow
all shapes in plan-list order. It does not reroute, resize, move, restyle, or repair
the plan.

## Hard failures

Compilation first runs construction-plan semantic validation, then rejects:

- duplicate element IDs or port names;
- out-of-page regions, routes, labels, callouts, or leader points;
- text boxes outside their owning shapes;
- children outside a containing parent's padding or header exclusion area;
- zero-length or non-orthogonal route segments where prohibited;
- waypoints or connector segments intersecting unrelated shapes or shape labels;
- callouts that overlap unrelated shapes or other callouts;
- leaders that do not start at their callout and end at the declared target; and
- target anchors outside their referenced objects.

All geometry is finite because both the planning schema and IR reject non-finite
numbers. Style tokens, formulas, and package instructions are closed by strict
schemas: unknown fields and unsupported token values fail before compilation.

The version 1 connector-label contract supplies an anchor and offset rather than
a text rectangle. G4 validates that anchor against page bounds; rendered text
extent measurement belongs to G6. No text dimensions are inferred here.

## V1 migration adapter

`compile_v1_design` converts a validated `DiagramDesign` to the same IR and marks
it `source_engine="v1_compatibility"`. It retains V1 native-master mapping,
dynamic center-to-center routing, connector styling, and existing neutral shape
defaults. Page orientation is derived from its dimensions; zero margin and a
one-inch grid are compatibility metadata only. This adapter is migration support,
not the Generation v2 planning path.
