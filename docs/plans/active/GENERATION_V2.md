# Visiogen Generation v2 Implementation Plan

**Status:** Active; G0-G4 complete, G5 locally verified, G8 CLI vertical path complete

**Date:** 2026-09-03

**Working feature name:** AI-directed native Visio generation

**Goal:** Produce professional-quality, editable native VSDX diagrams by giving
AI authority over the complete visual construction plan while retaining
deterministic package safety, validation, provenance, and Microsoft Visio
acceptance.

**Relationship to the current pipeline:** This is an incremental replacement of
the generation core, not a rewrite of the provider, template, package-safety,
preview-export, evidence, or native-acceptance infrastructure. The current
generation path remains available until Generation v2 passes its release gate.

## 1. Product decision

Generation v2 separates three contracts that the current `DiagramDesign` partly
combines:

1. `DiagramSpecification` records what the diagram must communicate.
2. `VisioConstructionPlan` records exactly how the diagram should look and route.
3. `VisualEditPatch` records bounded changes made after inspecting a real Visio
   preview.

The AI owns semantics, visual hierarchy, composition, shape selection, exact
geometry, ports, connector routes, label placement, callout placement, and visual
revisions. Code validates and compiles those decisions into known-good native
Visio structures. The model does not directly own arbitrary package relationships,
content types, master parts, or unconstrained VSDX XML in the production path.

```text
natural language ---------+
professional spec --------+-> normalized DiagramSpecification
analysis bundle ----------+                 |
                                            v
                                  AI construction planner
                                            |
                                            v
                                  VisioConstructionPlan
                                            |
                              validate -> compile -> VSDX
                                            |
                                  Microsoft Visio preview
                                            |
                                   AI visual inspector
                                            |
                          approve or validated VisualEditPatch
                                            |
                              bounded rerender/review loop
                                            |
                              native lifecycle acceptance
```

## 2. Preserved and replaced boundaries

### Preserve

- Codex CLI structured and multimodal provider adapters;
- configuration and CLI dispatch infrastructure;
- prompt, response, timing, source-revision, and checksum provenance;
- canonical native Visio template and master inventory;
- safe package serialization and atomic output handling;
- structural VSDX validation;
- Microsoft Visio preview export;
- Windows open/move/save/close/reopen automation; and
- existing Generation v1 tests until their replacement behavior is accepted.

### Replace or substantially extend

- the current shallow `DiagramDesign` contract;
- `LayoutResult` as the complete renderer input;
- implicit or automatic connector routing as the normal path;
- broad semantic-to-shape defaults when explicit choices are available;
- whole-design replacement for every visual correction; and
- the single unverified critique/revision pass.

### Keep only as fallback or research

- Graphviz and deterministic layered layout;
- whole-shape automatic routing when an explicit route is unavailable; and
- direct AI-authored VSDX XML, isolated behind an experimental benchmark rather
  than used by the production pipeline.

## 3. Progress tracker

| Phase | Name | Status | Exit evidence |
|---|---|---|---|
| G0 | Baseline and contract freeze | Complete | Frozen corpus, rubric, baseline report, tests, and checkpoint lineage |
| G1 | Professional diagram specification | Complete | Schema, validators, fixtures, CLI parsing, provenance, and checkpoint lineage |
| G2 | Analysis-to-generation bridge | Complete | Import boundary, reviewed draft workflow, fidelity tests, provenance, and checkpoint lineage |
| G3 | AI construction planner | Complete | Valid plans for all core families from real `gpt-5.6-sol`; checkpoint lineage |
| G4 | Construction-plan validation and compiler IR | Complete | Hard-validation and deterministic compilation tests; checkpoint lineage |
| G5 | Native renderer v2 | In progress | Linux structural gate passes; Windows native lifecycle pending |
| G6 | Visual measurement and diagnostics | Deferred | Machine-readable geometry and preview diagnostics |
| G7 | Iterative AI visual editing | Deferred | Bounded patch loop with final re-approval |
| G8 | Vertical Generation v2 pipeline | Complete for local CLI scope | Text, spec, and analysis inputs reach the v2 renderer with common evidence |
| G9 | Quality corpus and comparative evaluation | Not started | v2 beats frozen v1 baseline and passes thresholds |
| G10 | Windows native acceptance and cutover | Not started | Checksum-bound native and human acceptance |
| GX | Direct-XML research experiment | Optional | Comparative feasibility report; no release dependency |

Only change a phase to `Complete` when its exit gate and evidence are committed or
checksum-bound in an immutable external acceptance directory. Unit tests alone do
not close real-model, visual-quality, or native-Visio gates.

## 4. Phase plan

### G0 — Baseline and contract freeze

**Purpose:** Establish measurable evidence before changing the architecture.

Work:

- Freeze a Generation v2 development corpus containing at least:
  - branching flowchart;
  - system architecture;
  - contained component schematic;
  - dense multi-branch process;
  - nested-container architecture;
  - callout-heavy patent-oriented schematic;
  - long-label case;
  - reciprocal and self-loop connector case;
  - style-constrained professional case; and
  - one PDF or DOCX reconstruction case.
- Preserve the original request, professional specification where applicable,
  expected semantic inventory, and required/forbidden visual conditions.
- Run the current pipeline where Windows Visio is available and retain exact V1
  artifacts as the baseline.
- Define a human review rubric and deterministic measurements for semantic
  completeness, label readability, overlap, connector crossings, connector-to-
  label obstruction, arrow direction, containment, balance, and native behavior.
- Record current limitations, including unused connector-side hints and lack of
  final-preview re-approval.

**Exit gate:** The corpus, rubric, baseline report format, and source revision are
frozen. Missing Windows baseline cases may be marked unavailable, never inferred.

**Current evidence:** The ten-case corpus, frozen thresholds, strict evaluation
contracts, reproducible baseline builder, quality rubric, and incomplete-but-honest
Generation v1 baseline are implemented and locally verified. See
[`../../acceptance/G0_GENERATION_V2_BASELINE.md`](../../acceptance/G0_GENERATION_V2_BASELINE.md).
The phase is closed by the checkpoint lineage recorded there.

**Phase completion record:**

```text
Phase: G0 — Baseline and contract freeze
Status: Complete
Baseline source revision: 2c56b13
Corpus/schema commit: 51ad0e2
Baseline evidence commit: f9b9abc
Evaluation documentation commit: 9ba57e2
Deterministic tests: 263 generation-owned; 537 full repository
Real-provider evidence: unavailable for the frozen corpus; explicitly recorded
Windows/Visio evidence: unavailable for the frozen corpus; explicitly recorded
Review decision: contract complete; Generation v1 quality baseline incomplete
Known limitations carried forward: current Windows V1 comparison unavailable
```

### G1 — Professional `DiagramSpecification`

**Purpose:** Replace ambiguous prose as the only source contract.

Work:

- Define a versioned strict schema covering:
  - diagram purpose, audience, notation, and orientation;
  - objects, relationships, labels, reference numerals, and containment;
  - required and optional content;
  - semantic importance and primary visual flow;
  - drafting conventions and shape-family preferences;
  - ordering, adjacency, alignment, and separation constraints;
  - permitted ambiguity and explicit unknowns; and
  - measurable visual requirements and forbidden conditions.
- Support JSON and YAML input without executable extensions or template syntax.
- Add `--spec-file` while retaining `--text`.
- Add deterministic schema, reference, cycle, and constraint validation.
- Define a model-assisted natural-language-to-spec adapter whose output must pass
  the same validation and remain visible to the user.

**Exit gate:** Expert-authored fixtures round-trip without information loss;
invalid references and contradictory hard constraints fail with actionable
findings; text mode produces a persisted, validated specification.

**Current evidence:** The strict version 1 schema, safe JSON/YAML loader,
deterministic reference/containment/constraint validation, bounded text adapter,
`--spec-file` input, downstream design handoff, and checksum-bound specification
provenance are implemented. Focused specification/CLI/pipeline tests pass, and the
generation-owned gate passes with 271 tests. See
[`../../generation/DIAGRAM_SPECIFICATION.md`](../../generation/DIAGRAM_SPECIFICATION.md).
The implementation and its evidence are committed at `b6c523a`.

**Phase completion record:**

```text
Phase: G1 — Professional DiagramSpecification
Status: Complete
Engineering contract commit: ffb053a
Implementation and evidence commit: b6c523a
Focused specification/CLI/pipeline/boundary tests: 31 passed
Generation-owned tests: 271 passed in 36.45s
Full repository tests: 545 passed in 45.90s
Package build: passed
CLI help check: passed
Real-provider evidence: not required to close G1; no quality claim made
Windows/Visio evidence: not required to close G1; no native claim made
Review decision: G1 exit contract satisfied
```

### G2 — Analysis-to-generation bridge

**Purpose:** Turn evidence-grounded document analysis into editable generation
input without making analysis depend on generation internals.

Work:

- Define a versioned import boundary rather than directly importing analysis
  package models.
- Project analyzed objects, relationships, directions, grouping, visible labels,
  reference numerals, uncertainty, and evidence references into a draft
  `DiagramSpecification`.
- Preserve unsupported or uncertain observations as review items instead of
  silently converting them into facts.
- Emit a human-reviewable intermediate specification before generation.
- Add `--analysis-bundle` and an option to stop after specification creation.

**Exit gate:** At least one PDF and one DOCX analysis bundle produce validated
draft specifications; a reviewer can correct the spec and generate from the
corrected artifact; evidence provenance survives the bridge.

**Current evidence:** A generation-owned version 1 import boundary validates and
checksum-verifies analysis manifests, analyzed diagrams, and visual-evidence
references without importing analysis modules. Synthetic PDF and DOCX bundle
fixtures project into strict draft specifications; supported semantics and
provenance survive, while uncertain or unsupported observations become review
items. The CLI supports explicit multi-candidate selection and can stop after
atomically publishing a human-reviewable JSON specification. See
[`../../generation/ANALYSIS_IMPORT.md`](../../generation/ANALYSIS_IMPORT.md).
Focused bridge/specification/CLI/pipeline/boundary tests pass with 60 tests; the
generation-owned gate passes with 279 tests and the full repository gate with 553
tests. Package build and CLI help checks pass. The implementation and evidence are
committed at `f95d48d`.

**Phase completion record:**

```text
Phase: G2 — Analysis-to-generation bridge
Status: Complete
Implementation and evidence commit: f95d48d
PDF bundle projection: passed
DOCX bundle projection: passed
Reviewer correction and --spec-file reload: passed
Evidence/checksum tamper rejection: passed
Focused bridge/specification/CLI/pipeline/boundary tests: 60 passed
Generation-owned tests: 279 passed in 36.21s
Full repository tests: 553 passed in 44.99s
Package build: passed
CLI help check: passed
Real-provider evidence: not required to close G2; no quality claim made
Windows/Visio evidence: not required to close G2; no native claim made
Review decision: G2 exit contract satisfied
```

### G3 — AI `VisioConstructionPlan`

**Purpose:** Give the model explicit control over all important visual decisions.

Work:

- Define a strict, versioned construction schema containing:
  - page size, orientation, margins, grid, regions, and guides;
  - exact native shape/style selections;
  - shape rectangles, text boxes, typography, fill, line, and z-order;
  - container headers, padding, membership, and clipping policy;
  - named ports and connection sides;
  - connector type, route, waypoints, bends, jumps, and arrowheads;
  - connector-label position, offset, orientation, and background;
  - callout carrier, target anchor, and leader route; and
  - visual rationale and constraint traceability.
- Rewrite prompts around the professional specification and measurable drafting
  rules, with few-shot examples drawn only from approved fixtures.
- Add one bounded plan-repair call for schema or hard-constraint failures.
- Version prompts and schemas in provenance.

**Exit gate:** A real `gpt-5.6-sol` run produces valid complete construction plans
for every core diagram family. Fake providers prove plumbing only.

**Current evidence:** The version 1 `VisioConstructionPlan`, completeness and
semantic validator, prompt/example versioning, three approved-fixture patterns,
one-repair planner, failure provenance, and clean-source real-model acceptance
runner are implemented. Deterministic tests cover complete round trips, semantic
drift, containment, callouts, traceability, bounded repair, prompt restrictions,
and provenance. See
[`../../generation/CONSTRUCTION_PLAN.md`](../../generation/CONSTRUCTION_PLAN.md).
Focused G3 tests pass with 24 generation tests, the generation-owned gate passes
with 285 tests, and the full repository gate passes with 559 tests. Ruff checks,
the package build, and acceptance-runner CLI check pass.
The corrected clean-checkpoint real `gpt-5.6-sol` gate passed all three core
families. See
[`../../acceptance/G3_CONSTRUCTION_PLANNER.md`](../../acceptance/G3_CONSTRUCTION_PLANNER.md).

**Phase completion record:**

```text
Phase: G3 — AI VisioConstructionPlan
Status: Complete
Construction schema commit: f5aaff6
Planner and deterministic tests commit: 6f4496b
Acceptance tooling/documentation commit: 501a32a
Real-run feedback correction commit: 0df508d
Real provider/model: codex / gpt-5.6-sol
Clean source revision: 0df508defe66eeebce47315fe4ea06277d37c0a7
Core-family plans: flowchart passed; system_block passed; component_schematic passed
External evidence inventory SHA-256: 354b4c92fafcef5251643bcd8d26784a808ec648355c55f24fdcd1eb5561a37c
Generation-owned tests: 285 passed in 38.09s
Full repository tests: 559 passed in 46.21s
Package build: passed
Review decision: G3 exit contract satisfied
```

### G4 — Construction-plan validation and compiler IR

**Purpose:** Make deterministic code a faithful compiler rather than a visual
designer.

Work:

- Introduce a renderer-neutral validated IR with resolved native master names,
  styles, ports, routes, label geometry, callouts, and z-order.
- Validate finite geometry, bounds, containment, port ownership, route continuity,
  waypoint clearance, label bounds, callout clearance, and supported style tokens.
- Detect intersections between connectors and unrelated nodes or labels.
- Reject unsupported formulas and package instructions.
- Produce precise findings addressable by a plan repair or later patch.
- Retain a compatibility adapter from the V1 design during migration.

**Exit gate:** Compilation is deterministic for a given validated plan; it makes no
undocumented aesthetic decisions; malformed or impossible plans fail before VSDX
mutation.

**Current evidence:** A strict immutable renderer IR resolves native master names,
styles, port coordinates, route endpoints, label anchors, callouts, and z-order.
The compiler reports hard geometry and ownership failures before rendering,
rejects unsupported schema fields, and includes an explicitly tagged V1 migration
adapter. Focused deterministic and hard-failure tests pass. See
[`../../generation/COMPILER_IR.md`](../../generation/COMPILER_IR.md). The phase
is closed by the checkpoint lineage recorded below.

Local verification: 15 focused compiler/construction/boundary tests, 291
generation-owned tests, and 565 full-repository tests passed; package build and
CLI help smoke check also passed.

**Phase completion record:**

```text
Phase: G4 — Construction-plan validation and compiler IR
Status: Complete
Compiler implementation commit: 5e37704
Hard-validation tests commit: 11208a7
IR contract documentation commit: f664e86
Focused compiler/construction/boundary tests: 15 passed in 0.55s
Generation-owned tests: 291 passed in 51.67s
Full repository tests: 565 passed in 60.44s
Package build: passed
CLI help check: passed
Real-provider evidence: not required; compilation is deterministic
Windows/Visio evidence: deferred to G5 native renderer acceptance
Review decision: G4 exit contract satisfied
```

### G5 — Native renderer v2

**Purpose:** Render the complete AI-directed construction plan with editable native
Visio behavior.

Work:

- Extend the current safe renderer instead of replacing its package machinery.
- Implement explicit master selection and validated style tokens.
- Implement named ports and honor source/target attachment choices.
- Implement explicit orthogonal/polyline routes and waypoints.
- Implement connector-label placement independently of shape labels.
- Implement container padding, headers, membership, and z-order.
- Implement callout anchors and leader routes.
- Keep automatic dynamic routing only as an explicitly recorded fallback.
- Preserve unique IDs, relationship integrity, atomic output, and package checks.

**Exit gate:** Structural tests cover horizontal, vertical, diagonal, branching,
reciprocal, self-loop, nested-container, and callout cases. Generated files pass a
targeted Windows smoke test for clean open, edit, move, save, close, and reopen.

**Current evidence:** The template-based renderer consumes the immutable G4 IR and
materializes explicit native masters, geometry, styles, named connection points,
routes, connector labels, container membership, callouts, and stable z-order.
Linux structural tests cover every required topology and validate the resulting
package. See
[`../../generation/NATIVE_RENDERER_V2.md`](../../generation/NATIVE_RENDERER_V2.md).
The phase remains open because desktop Microsoft Visio is unavailable in this
environment; the required move/save/close/reopen smoke test and manual review have
not been run.

The first Windows-opened structural stress fixture failed visual review: Visio
recalculated incomplete one-sided container membership, changing container and
member geometry, while the intentionally combined topology routes were unsuitable
as a professional acceptance sample. The renderer now records reciprocal native
membership, disables container auto-resize, fixes callout text geometry, and has a
separate restrained professional acceptance fixture. Windows re-validation of
that replacement candidate remains pending.

Post-remediation local verification: 56 focused compiler/renderer/package/boundary
tests, 295 generation-owned tests, and 569 full-repository tests passed; package
build also passed. Replacement candidate SHA-256:
`7c37bebb9e9586a69f9946e531813c84e6575068bfc89397facb916023b56b8c`.

Local verification: 55 focused compiler/renderer/package/boundary tests, 294
generation-owned tests, and 568 full-repository tests passed; package build and
CLI help smoke check also passed.

**Implementation checkpoint:**

```text
Phase: G5 — Native renderer v2
Status: In progress; Windows native lifecycle gate pending
IR completion commit: 5d1488b
Native renderer commit: 8ed9dda
Structural tests commit: fbeaefe
Renderer documentation commit: 47fea2e
Focused compiler/renderer/package/boundary tests: 55 passed in 33.32s
Generation-owned tests: 294 passed in 42.35s
Full repository tests: 568 passed in 51.27s
Package build: passed
CLI help check: passed
Windows/Visio evidence: unavailable in this Linux environment
Review decision: implementation accepted locally; phase remains open
```

### G6 — Visual measurement and diagnostics

**Purpose:** Give the critic objective facts in addition to pixels.

Work:

- Measure geometry-level overlaps, boundary violations, connector/node and
  connector/label intersections, route length, bends, crossings, alignment,
  whitespace, and minimum clearances.
- Export a diagnostic overlay image with stable object and edge identifiers.
- Keep measurements separate from aesthetic judgments.
- Record both pre-render plan measurements and post-render preview evidence.
- Define thresholds by diagram family instead of one universal density rule.

**Exit gate:** Synthetic fixtures prove each measurement; diagnostics identify the
correct IDs and regions; reports are stored in the evidence bundle.

### G7 — Iterative AI visual editing

**Purpose:** Replace whole-design one-shot correction with bounded, auditable
editing.

Work:

- Define strict `VisualEditPatch` operations such as move/resize shape, change
  style, reroute connector, change ports, move connector label, edit callout route,
  resize page, and adjust container padding.
- Make the critic inspect the original specification, construction plan, actual
  Visio preview, diagnostic overlay, and machine measurements.
- Validate every operation and its postconditions before mutating the plan.
- Permit a configurable maximum of three iterations initially.
- Stop on approval, repeated state, lack of measurable improvement, invalid patch,
  or budget exhaustion.
- Require the final rendered preview to receive an explicit approval call; a
  revised-but-unreviewed artifact cannot pass.
- Preserve every plan, patch, validation result, preview, and reason for stopping.

**Exit gate:** Tests prove iteration limits, cycle detection, rollback, immutable
history, and final-approval rules. Real runs demonstrate successful targeted edits
without semantic drift.

### G8 — Vertical Generation v2 pipeline

**Purpose:** Integrate the new contracts without prematurely deleting V1.

Work:

- Compose all three input modes: text, professional spec, and analysis bundle.
- Add an explicit `--generation-engine v1|v2` transition flag; do not silently
  change existing behavior during development.
- Publish a versioned evidence bundle containing the normalized specification,
  construction plans, validation results, compiler IR, VSDX candidates, previews,
  measurements, patches, final approval, provider identity, timings, and hashes.
- Report partial/failure states precisely.
- Add resume-from-spec and resume-from-plan workflows for professional iteration.

**Exit gate:** Every input mode completes a clean vertical run and produces the
same evidence contract. Failures cannot overwrite earlier evidence or masquerade
as approved output.

**Accepted local scope:** The public CLI now defaults to the v2 pipeline for all
three existing input modes. It persists the normalized specification, versioned
construction prompts and responses, validated construction plan, compiler IR,
rendered VSDX, provider identity, timings, source state, and hashes. Atomic path
handling prevents an output collision from overwriting reserved evidence. The
text-to-VSDX fake-provider vertical test renders and revalidates a real native VSDX;
the existing CLI and analysis-import tests cover professional specifications and
analysis bundles at the same boundary. The CLI reports elapsed-time progress for
each long-running and deterministic stage, with `--quiet` available for scripts.

A development-source real-provider run also completed through the public command
with `codex/gpt-5.6-sol`. It required two specification attempts and one
construction attempt, produced a structurally valid 402 KiB VSDX, and retained an
output SHA-256 of
`6c46ec6fe5c789399ef4201745ef598ecaf6ea64827436dd992db1d2f57ff3bb`.
The run recorded a dirty worktree and therefore proves integration behavior only;
it is not immutable release acceptance. The final local repository gate passes
with 571 tests, and the sdist/wheel build and CLI help checks pass.

The earlier transition-engine flag, resume-from-plan workflow, previews,
measurements, patches, and final visual approval are not necessary to make the v2
CLI usable and are deferred. The manifest reports that visual diagnostics and
editing were not performed and that Windows acceptance is pending. This local G8
decision makes no visual-quality or native-Windows acceptance claim.

### G9 — Quality corpus and comparative evaluation

**Purpose:** Establish that V2 is visibly and semantically better, not merely newer.

Work:

- Run the entire frozen corpus on one immutable clean revision using the declared
  production model and prompt/schema versions.
- Run multiple samples for selected prompts to measure stochastic reliability.
- Compare V2 with the frozen V1 baseline using blind human review where practical.
- Require semantic completeness and native correctness as non-negotiable gates.
- Proposed initial visual thresholds:
  - zero shape or label overlaps;
  - zero arrowheads inside unrelated shapes;
  - zero connectors crossing unrelated labels;
  - zero callout leaders crossing unrelated labels;
  - correct required direction and containment in every case;
  - no unresolved high-severity critic finding;
  - at least 80% of cases preferred over V1 by reviewers; and
  - at least 90% successful completion across repeated supported-scope runs.
- Calibrate thresholds during G0, but never weaken them after seeing V2 results
  without a documented rationale and a new evaluation version.

**Exit gate:** A checksum-bound evaluation passes the frozen semantic, visual,
reliability, and provenance rules. Targeted reruns cannot replace the full corpus.

### G10 — Windows native acceptance and cutover

**Purpose:** Make V2 the supported generation architecture.

Work:

- Run exact final candidates through desktop Microsoft Visio.
- Verify clean open, individual selection/editing, connector and callout attachment,
  route behavior after moving both endpoints, save, close, and reopen.
- Complete manual visual review against the professional specification and rubric.
- Record Visio version, exact source revision, model, prompt/schema versions, and
  hashes for every candidate and preview.
- Update the public architecture and release documentation.
- Make V2 the default only after acceptance; retain V1 for one deprecation window.
- Remove V1 adapters and Graphviz from the primary path in a later dedicated
  cleanup release, not in the acceptance commit.

**Exit gate:** All supported corpus cases pass automated native lifecycle checks and
manual visual review. The release record states the supported scope and remaining
limitations without borrowing evidence from document analysis.

Windows review of the first restrained candidate found a second native-rendering
failure: Visio reopened the package without warnings but reapplied master formulas,
restoring template sizes and displacing text, connectors, and callouts. The G5-only
renderer now writes explicit `No Formula` overrides for authoritative cached cells
while preserving dynamic connector glue formulas. Replacement candidate:
The second Windows screenshot then exposed inherited geometry inside grouped
container children, inherited text-block origins, and an undeleted third master
geometry row on each explicit connector. The third Windows screenshot confirmed
those fixes and isolated the remaining defect to the container master's nested
body subshape, which Visio detached from its correctly positioned header. The body
is now rendered directly on the container group root. The fourth Windows screenshot
showed correct containment and isolated one final inherited decorative geometry
section in the header; the header is now a single explicit rectangle. Replacement
The fifth Windows review showed that first-open appearance was correct but native
move/undo behavior still failed: explicit routes did not follow their endpoints,
callout leaders stayed behind, and removed instance children were inherited again
from the master. Suppressed master children are now retained with explicit deletion
markers, the acceptance routes use native movement-aware glue, and callout leader
ends reference target pins. Replacement candidate:
`artifacts/g5-professional-acceptance-v6.vsdx`,
SHA-256
`aaeb85078def9656c0f135ba07e5be71afbafe6dc3c57946db3099d24f09507c`.
The sixth Windows review still showed that undo could restore every moved instance
to the master transform's shared default point near the lower-left of the page.
The renderer had represented authoritative instance transforms as blocked
`No Formula` cells; undo could restore master inheritance instead of the instance's
original coordinate. Instance transforms now use explicit, unguarded numeric local
formulas, preserving editability while giving undo a stable local value to restore.
The Windows automation now performs move, undo, redo, save, close, and reopen with
exact coordinate and connection-signature assertions. Replacement candidate:
`artifacts/g5-professional-acceptance-v7.vsdx`, SHA-256
`a3bb0b64c09b04949f7aade9d70e0ec593dafaaedc5d6abae18dc27679e245ab`.
G5 remains in progress pending Windows review of that exact artifact.

A subsequent connector review confirmed that explicit routes had `Connect` rows
but still stored `BeginX`/`BeginY` and `EndX`/`EndY` as fixed page coordinates.
They could look attached while remaining geometrically static. Explicit connectors
now use live `PAR(PNT(...))` formulas against their exact named ports. Endpoint
geometry follows those formulas, connector transforms recalculate from the live
ends and fixed intermediate waypoints, and the Windows gate fails if any attached
endpoint stays stationary when its shape moves. Focused replacement candidate:
`artifacts/g5-connector-acceptance-v8.vsdx`, SHA-256
`08eaa99d99dc27893d46386e8d5808f9c34e07369a519470baa8b249bf53ff11`.

Windows movement of that candidate exposed four conflicting pieces of connector
metadata. Generated Type-0 connection points used outward rather than Visio-native
inward direction vectors; `Connect.ToPart` was hard-coded instead of accounting for
the named port's effective row after inherited master rows; the instance wrote the
page-only `RouteStyle` cell; and value `16` meant center-to-center rather than
straight routing. That combination let first-open cached geometry look plausible
but produced long loop-back rectangles on the first move. The renderer now uses
inward vectors, derives `ToPart` from the effective port row, writes
`ShapeRouteStyle`/`ConLineRouteExt`, and fixes explicit route geometry with
`ConFixedCode=2`. Orthogonal endpoint-adjacent bends follow their live endpoint.
The Windows gate now rejects metadata disagreement and straight-connector geometry
outside the begin/end envelope across move, undo, redo, save, and reopen. Focused
replacement candidate: `artifacts/g5-connector-acceptance-v9.vsdx`, SHA-256
`30f115a4cd56b62dba56d9aa3944797aaa6238e14aaaf10aeb47ad8b35e0864b`.

### GX — Constrained direct-VSDX XML research experiment

**Purpose:** Test the user's direct-authoring hypothesis without putting production
package safety at risk.

Work:

- Give the model an unpacked known-good candidate and a strict allowlist of mutable
  page parts.
- Prohibit edits to content types, relationships, masters, and unrelated package
  parts in the first experiment.
- Compare direct XML, construction-plan compilation, and V1 on the same small cases.
- Measure first-open success, repair warnings, visual quality, editability, movement
  behavior, save/reopen survival, token use, latency, and repair rate.
- Preserve every mutation and validation result in an isolated evidence directory.

**Exit gate:** Publish a feasibility report. Promotion into the production design
requires it to outperform the construction-plan approach while passing the same
native lifecycle and safety gates. This experiment must not block G0-G10.

## 5. Cross-phase engineering rules

1. AI-quality claims require real-provider evidence; fake transports prove only
   contracts and orchestration.
2. Visual-quality claims require a preview exported by desktop Microsoft Visio.
3. Native behavior claims require open/move/save/close/reopen evidence from Visio.
4. Every schema and logical prompt is versioned and checksum-bound.
5. No model response may directly introduce arbitrary filesystem paths, commands,
   XML relationships, or package parts into the production compiler.
6. A visual patch may not change required semantics unless the specification is
   explicitly revised and revalidated.
7. All intermediate artifacts are immutable within a run.
8. The analysis workstream remains independent; integration uses a versioned data
   artifact rather than package imports.
9. Existing user changes and historical acceptance evidence are never overwritten.
10. Completion status is updated only with links to the exact evidence that closes
    the phase.

## 6. Recommended implementation structure

New Generation v2 code should live under `src/visiogen/generation/`:

```text
generation/
  specification.py       # professional semantic/drafting contract
  specification_io.py    # JSON/YAML admission and validation
  analysis_import.py     # versioned analysis-artifact projection
  construction.py        # AI construction-plan schema
  planning.py            # model workflow and plan repair
  compiler.py            # validated plan -> renderer IR
  diagnostics.py         # geometry and preview measurements
  patches.py             # visual-edit operations and validation
  refinement.py          # bounded render/inspect/patch loop
  evidence.py            # versioned Generation v2 artifact bundle
  pipeline_v2.py         # orchestration
```

The existing `renderer.py`, `preview.py`, provider adapters, template, and Windows
scripts should be extended behind compatible boundaries until V2 acceptance. Avoid
a broad namespace migration before G8.

## 7. Phase completion record template

Append this block when closing a phase:

```text
Phase:
Status: Complete
Source revision:
Schema/prompt versions:
Deterministic tests:
Real-provider evidence:
Windows/Visio evidence:
Review decision:
Known limitations carried forward:
```
