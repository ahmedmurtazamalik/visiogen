# Visiogen Hybrid-AI Migration Plan

> **Archived migration record.** This plan replaced the geometry-free,
> deterministic-output assumptions in the baseline plans and was implemented on
> 2026-08-20. Current architecture lives in
> [`../../architecture/HYBRID_AI.md`](../../architecture/HYBRID_AI.md).

**Project class:** exploratory single-developer MVP
**Time budget:** 3–4 focused days
**Goal:** replace the semantics-only AI boundary with a working hybrid pipeline in which a real multimodal model designs the diagram, code enforces hard constraints and native Visio integrity, and one image-based critique pass can revise the composition.

## Contract freeze

### Required behavior

- A real provider creates a structured diagram design from text.
- The design may include stochastic geometry and visual intent.
- Code validates references, containment, geometry, page bounds, and package structure.
- One AI repair attempt may correct rejected design data.
- Valid AI geometry is preserved; Graphviz is an explicit fallback only.
- The renderer emits editable native Visio shapes, callouts, and dynamically glued connectors.
- A preview image is inspected by a real image-capable provider.
- At most one structured visual revision is applied and rerendered.
- Debug artifacts expose prompts, responses, designs, validation, previews, model identity, and final checksum.

### Preserved behavior

- Existing `DiagramGraph`, shape mapping, template, renderer, and structural tests continue to work.
- Provider selection remains explicit; no silent fallback.
- AI does not author VSDX package XML or ShapeSheet formulas.
- Microsoft Visio remains the native acceptance authority.

### Explicit exclusions

- multiple autonomous critique loops;
- candidate swarms or agent orchestration;
- multi-page documents;
- CAD/physical geometry;
- production deployment;
- perfect routing;
- filing-readiness claims.

## Day 1 — Design contract and hard guardrails

### H1. Structured design model

**Files:**
- create `src/visiogen/design.py`
- create `tests/test_design.py`
- modify provider schema support only as needed

Define:

- `DiagramDesign`
- `LayoutPlan`
- `NodePlacement`
- optional connector-side hints
- `DesignResult` with safe provider metadata

The design contains the semantic graph plus layout intent and optional complete geometry. It supports stochastic outputs; no exact-output promise is made.

**RED/GREEN gate:** a design with complete geometry converts to a canonical graph and retains visual intent; malformed references and unknown placement IDs fail.

### H2. Geometry guardrails

**Files:**
- create `src/visiogen/hybrid_layout.py`
- create `tests/test_hybrid_layout.py`

Implement hard checks for geometry coverage, positive size, bounds, ordinary-node overlap, and one-level containment. Preserve a valid AI layout. Permit bounded page fitting and container expansion. Return structured validation findings suitable for a model repair prompt.

**RED/GREEN gate:** valid AI geometry survives unchanged except documented page fitting; invalid geometry produces precise findings rather than silently invoking Graphviz.

### H3. AI designer workflow

**Files:**
- create `src/visiogen/designer.py`
- create `tests/test_designer.py`
- extend Codex structured runner without duplicating process logic

Build a structured system prompt that asks the model to perform semantic planning, composition, hierarchy, and geometry together. Permit one repair call with hard-validation feedback.

**Real gate:** run one representative prompt through the production Codex CLI adapter and preserve the exact design artifact. Fake-runner tests prove only plumbing.

**Commit:** `Add hybrid AI diagram design contract`

## Day 2 — Working text-to-VSDX vertical slice

### H4. Compose the pipeline

**Files:**
- implement `src/visiogen/pipeline.py`
- create `tests/test_pipeline.py`
- extend `src/visiogen/cli.py`
- create `tests/test_cli.py`

Implement a public generation path that performs:

```text
text → real/injected designer → hard validation → hybrid layout → renderer → structural validation
```

Write atomically:

- `01-request.txt`
- `02-design-response.json`
- `03-validated-design.json`
- `04-layout.json`
- `05-initial.vsdx`
- provider/model/timing manifest

The CLI exposes explicit provider/model selection and a debug directory.

**Real gate:** generate one editable VSDX from a fresh text request—not a checked-in graph fixture—and validate the package.

**Commit:** `Compose hybrid text to Visio pipeline`

## Day 3 — Visual critique and one-pass revision

### H5. Preview export

**Files:**
- create `src/visiogen/preview.py`
- create `tests/test_preview.py`

Export the actual VSDX through desktop Microsoft Visio on Windows behind an injected command boundary. Fail explicitly when Visio is unavailable; do not substitute another VSDX renderer or claim visual critique without a Visio-exported image.

### H6. Structured multimodal critic

**Files:**
- create `src/visiogen/critic.py`
- create `tests/test_critic.py`
- add image support to the Codex structured runner

Define:

- `VisualIssue`
- `VisualCritique`
- `LayoutRevision`

The critic sees the actual PNG, original request, and design. It checks source fidelity, hierarchy, spacing, balance, labels, crossings, obstruction, and connector clarity. It returns approval or one complete revised placement set.

### H7. Bounded rerender

Update the pipeline to preserve the initial artifact, apply at most one valid revision, rerender, revalidate, and export a final preview. Never loop indefinitely.

**Real gate:** run Codex with `--image` against the generated preview, preserve its structured critique, and prove the revised or approved final artifact came from that response.

**Commit:** `Add visual critique and bounded rerender`

## Day 4 — Real acceptance and cleanup

### H8. Three-case live corpus

Run fresh real-provider cases:

1. branching flowchart;
2. left-to-right system diagram;
3. contained component schematic with callouts.

For every case preserve prompts, responses, validation, initial/final designs, initial/final previews, and VSDX checksums. Evaluate hard invariants and a simple visual rubric; do not compare exact JSON strings.

### H9. Native Visio gate

Package the three exact artifacts for Windows. Acceptance requires:

- open without repair;
- labels and shapes editable;
- connectors remain glued after moving both endpoints;
- acceptable initial composition;
- save, close, and reopen.

### H10. Documentation and review

Update README and milestone docs to distinguish:

- unit/contract evidence;
- real text-model evidence;
- real image-critic evidence;
- structural package evidence;
- Microsoft Visio evidence.

**Commit:** `Validate hybrid AI diagram generation`

## Acceptance rules

1. Fake transports may never close an AI-quality gate.
2. A checked-in expected JSON fixture may never be presented as provider output.
3. Every real AI artifact records provider and exact model.
4. Stochastic differences are allowed; every output must still satisfy hard constraints.
5. The initial and revised artifacts are both retained.
6. An image critic must receive an actual generated image.
7. No Windows-native behavior is claimed from Linux structural checks.
8. A new feature enters this migration only by replacing another item at equal or lower effort.
