# Generation Pipeline Evolution

Visiogen has used three main generation architectures. Each iteration moved more
visual-design responsibility to AI while preserving deterministic validation,
native VSDX construction, and Microsoft Visio acceptance.

## 1. Deterministic semantic-extraction pipeline

The original baseline treated the model as a semantic extractor:

```text
Natural-language request
→ provider-specific extraction into a geometry-free DiagramGraph
→ deterministic normalization and reference validation
→ Graphviz layout, with a deterministic layered fallback
→ deterministic semantic-to-template visual mapping
→ template-based native VSDX rendering
→ structural and Microsoft Visio validation
```

Local Qwen through `llama.cpp`, Gemini, and Codex CLI were tried behind a common
extraction contract. Codex CLI became the preferred extractor. Graphviz was the
primary layout engine; a custom layered strategy covered unavailable or unsuitable
Graphviz execution.

This approach produced predictable, editable native diagrams, but code owned
nearly every visual decision. Results tended to be mechanically arranged, and
Windows testing exposed recurring connector-routing, cached-endpoint, callout,
spacing, and movement problems.

The archived baseline plans and M4–M6 acceptance records preserve this design and
its evidence.

## 2. Hybrid AI designer pipeline — Generation v1

The hybrid migration promoted the model from extractor to diagram designer:

```text
Natural-language request
→ AI DiagramDesign with semantics, hierarchy, composition, and geometry
→ deterministic hard validation
→ at most one AI repair for correctable validation failures
→ hybrid layout normalization
→ template-based native VSDX rendering and structural validation
→ Microsoft Visio preview
→ multimodal visual critique
→ at most one whole-design revision and rerender
```

Valid AI geometry was preserved, while Graphviz became an explicit fallback
instead of the default visual authority. The pipeline retained structured prompts,
responses, designs, validation findings, previews, provider identity, timings, and
checksums.

The architecture improved composition and hierarchy, but `DiagramDesign` still
combined semantic and visual responsibilities too loosely. Connector-side hints
did not provide complete routing control, the renderer continued to make implicit
visual decisions, and critique replaced the whole design rather than expressing a
small targeted edit. The historical three-case hybrid bundle also skipped the
visual-critique stage and retained no final previews, so it is not a complete
Generation v1 quality baseline.

Generation v1 remains the legacy path while Generation v2 proceeds through its
release gates.

## 3. AI-directed construction and compiler pipeline — Generation v2

Generation v2 separates the source, construction, and revision responsibilities:

```text
Natural language / professional specification / analysis bundle
→ validated DiagramSpecification
→ AI VisioConstructionPlan
→ deterministic validation and compilation into renderer-neutral IR
→ native VSDX renderer v2
→ Microsoft Visio preview and deterministic visual diagnostics
→ bounded AI VisualEditPatch loop
→ preview re-approval and native lifecycle acceptance
```

The three principal contracts are:

- `DiagramSpecification`: what the diagram must communicate.
- `VisioConstructionPlan`: exactly how the diagram should look and route.
- `VisualEditPatch`: bounded changes after inspecting the rendered result.

The model explicitly owns page composition, regions, native shape and style
selection, rectangles, typography, ports, connector routes and labels, callouts,
leaders, and z-order. Deterministic code validates those decisions, resolves them
into known-good template and native Visio structures, and compiles the VSDX
without inventing undocumented aesthetics.

As of 2026-09-03, G0–G4 are complete. The G5 renderer is implemented and passes
Linux structural verification, while its Windows native-Visio lifecycle gate is
pending. Visual diagnostics, iterative patching, vertical v2 integration,
comparative evaluation, and final cutover remain later phases.

## Deferred or experimental alternatives

- Direct AI-authored VSDX XML is reserved for an optional research benchmark. It
  is not a production architecture because arbitrary package authorship weakens
  safety and editability guarantees.
- Multiple generated candidates, candidate swarms, and unbounded agentic revision
  loops have been discussed but deliberately deferred. Implemented generation
  paths use bounded repair and revision behavior.

In short, the architectural progression is:

```text
AI extracts meaning; code designs
→ AI proposes the design; code constrains it
→ AI authors an explicit construction plan; code validates and compiles it
```

Authoritative current behavior is defined by
[`../architecture/HYBRID_AI.md`](../architecture/HYBRID_AI.md) and
[`../plans/active/GENERATION_V2.md`](../plans/active/GENERATION_V2.md). Historical
details are retained under `docs/plans/archive/` and `docs/acceptance/archive/`.
