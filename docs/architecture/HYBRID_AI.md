# Visiogen Hybrid-AI Architecture

**Status:** Authoritative architecture adopted 2026-08-20
**Scope:** Single-developer, 3–4 day migration MVP
**Product goal:** Produce editable native Visio first drafts whose semantics and composition benefit from a strong multimodal LLM, while application code enforces hard structural and package-safety constraints.

## 1. Product principle

Visiogen is no longer designed around deterministic output. Different valid runs may produce different diagrams, and that variation is desirable when it yields better compositions or interpretations.

Deterministic code remains as a guardrail, not the creative authority. It owns facts that must be mechanically true: schema validity, unique IDs, valid references, positive dimensions, page bounds, containment, readable package structure, and native Visio editability. AI owns judgment-heavy choices: what to emphasize, how to group information, what composition best communicates the source, and how to improve a rendered draft.

## 2. Runtime pipeline

```text
User description
  → AI diagram designer
      semantics + shape choices + visual hierarchy + layout proposal
  → hard validation
      schema, references, containment, geometry, bounds
  → bounded AI repair when validation reports a correctable problem
  → hybrid layout
      preserve valid AI composition; use code to fit/clamp/resolve hard violations
  → native Visio renderer
  → structural VSDX validation
  → preview export
  → multimodal AI visual critic
      inspect the actual rendered image against the original request
  → at most one structured revision pass in the MVP
  → rerender + revalidate + final preview
  → Microsoft Visio acceptance
```

The first rendered draft and revised draft are both preserved. The application never hides which one was selected or what the critic changed.

## 3. AI diagram-design contract

The model returns one structured `DiagramDesign` containing:

- source-faithful nodes, edges, labels, types, containment, and reference numerals;
- diagram orientation and composition style;
- visual importance and grouping hints;
- complete preferred node rectangles in page inches when it can provide them;
- preferred source/target connector sides where useful;
- concise design rationale for auditability, not for rendering.

The model may be stochastic. Temperature and sampling are provider configuration rather than being forced to zero globally.

The model does not emit VSDX XML, master IDs, relationship IDs, or ShapeSheet formulas. Those are implementation details that remain owned by the renderer.

## 4. Hybrid validation and normalization

Validation is split by responsibility.

### Hard code checks

Code rejects or reports:

- duplicate or empty node IDs;
- edges or hints referencing missing entities;
- invalid containment and containment cycles;
- unsupported semantic and visual types;
- incomplete or non-positive geometry;
- boxes outside the page;
- ordinary-node overlap above tolerance;
- children outside their containers;
- malformed VSDX packages or native-object references.

### AI-assisted repair

When the design is schema-valid but violates a correctable structural rule, the model receives the original request, its previous design, and concise machine-produced errors. It may return one corrected design. The same hard checks run again. A second invalid result fails clearly; the application does not normalize serious errors away or silently substitute a different provider.

Mechanical canonicalization—trimming IDs, assigning missing edge IDs, and stable reference lookup—may remain deterministic. Ambiguous semantic decisions are not silently made by normalization code.

## 5. Hybrid layout

AI-proposed geometry is now a first-class input. Valid proposed geometry is preserved rather than discarded and replaced by Graphviz.

Application code may make bounded mechanical adjustments:

- shift all content to satisfy page margins;
- grow the page;
- enforce minimum readable shape sizes;
- expand a container around its children;
- resolve a small overlap using the least-disruptive move.

If geometry is absent or remains invalid after the bounded repair, Graphviz is an explicit fallback candidate—not the definition of the product. Its output is labeled as fallback evidence.

The MVP generates one AI composition per run. A later extension may generate multiple candidates and let the visual critic rank them.

## 6. Rendering boundary

The renderer continues to copy known-good native Visio template objects. It maps semantic types to native shapes, applies the chosen geometry, creates editable labels and callouts, and creates native dynamically glued connectors.

The AI never directly edits package XML. This boundary protects editability and prevents a visually creative model response from corrupting the document format.

## 7. Visual feedback loop

After rendering, Visiogen exports a PNG preview and sends it to an image-capable model with:

- the original user request;
- the structured design used for rendering;
- a rubric covering readability, hierarchy, spacing, crossings, obstruction, balance, and source fidelity.

The critic returns structured data:

- approval or revision recommendation;
- issue type and severity;
- affected node/edge IDs;
- a concise explanation tied to visible evidence;
- a complete revised layout proposal or bounded geometry changes.

The MVP permits one critique-driven rerender. The final report preserves the initial design, initial preview, critique, revised design, revised preview, provider/model identity, and timing. Microsoft Visio remains authoritative for native connector movement and save/reopen behavior.

## 8. Provider model

Provider selection is explicit. Codex CLI with `gpt-5.6-sol` is the first preferred implementation because it is configured locally, supports strict structured output, and accepts image attachments. Gemini and local OpenAI-compatible models remain provider options when their text and image capabilities satisfy the same contracts.

Text design and image critique are separate capabilities. A provider may implement one or both. The pipeline must never pretend that a text-only provider performed visual critique.

## 9. Testing and acceptance

Fake transports are limited to request construction, schema parsing, typed failures, and orchestration tests. They are never evidence of model quality.

Every claimed AI capability requires a real-provider acceptance artifact containing:

- exact provider and model identity;
- exact prompts and structured responses;
- source description;
- initial and revised designs;
- initial and revised previews;
- validation findings;
- whether a repair or critique pass occurred;
- final VSDX checksum.

Stochastic quality is evaluated with rubrics and hard invariants rather than exact JSON equality. The MVP acceptance set includes at least one flowchart, one system diagram, and one contained component schematic. Each final file must pass structural validation, and selected files must pass Microsoft Visio open/move/save/close/reopen acceptance.

## 10. Bounded migration scope

### Included now

1. Introduce the structured AI design/layout contract.
2. Permit AI geometry and visual-intent fields.
3. Add hard geometry validation and bounded AI repair.
4. Compose a working text-to-VSDX pipeline using the real Codex provider.
5. Export the actual VSDX through desktop Microsoft Visio and run one real multimodal critique/revision pass against that Visio-exported image.
6. Preserve complete provenance artifacts.
7. Run real-provider acceptance before claiming the migration works.

### Deferred

- unbounded autonomous iteration;
- multi-page generation;
- more than one critique revision in the MVP;
- learned routing or direct AI-authored ShapeSheet formulas;
- automatic provider fallback;
- production service deployment;
- CAD or filing-ready patent drawings.

## 11. Definition of done

The architecture is adopted—not merely documented—when a real source description travels through the preferred model, produces a structured design with layout intent, passes hard validation, renders to native VSDX, is exported to an image by desktop Microsoft Visio, is visually critiqued from that image by a real image-capable model, receives at most one structured revision, rerenders successfully, and leaves auditable artifacts for every stage. Unit tests or third-party VSDX renderers cannot close this gate.

### Template-master retention

The MVP deliberately retains all masters from `templates/template.vsdx`. Direct package analysis found 19 master definitions; the representative basic-system output references four and leaves 15 unused. This is harmless package bloat, not evidence that all palette shapes remain on the page. Pruning is deferred because it must atomically update `masters.xml`, `masters.xml.rels`, `[Content_Types].xml`, master parts, and any per-master relationships, then pass desktop Microsoft Visio save/reopen acceptance.
