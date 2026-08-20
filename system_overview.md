# Visiogen — Hybrid-AI System Overview

## What Visiogen is

Visiogen turns a natural-language description into an editable Microsoft Visio `.vsdx` first draft. It targets flowcharts, system and architecture block diagrams, and abstract component or patent-oriented schematics with containers, connectors, reference numerals, and callouts.

The system is not meant to reproduce a physical product accurately from prose or create filing-ready patent drawings. Its purpose is to create a useful, native Visio starting point that communicates the requested structure and can be refined by a person.

## Architectural direction

Visiogen uses a hybrid architecture. AI is not limited to identifying shapes and relationships, and the product does not require identical output from repeated runs. A capable model participates in semantic interpretation, visual hierarchy, composition, layout, repair, and post-render visual review.

Application code remains responsible for hard correctness. It verifies IDs and references, checks containment and page geometry, prevents structurally invalid data from reaching the renderer, creates the native Visio package, and validates that package. This gives the model room to design without asking it to manage fragile VSDX XML or ShapeSheet formulas.

The authoritative detailed contract is `docs/HYBRID_AI_ARCHITECTURE.md`. The bounded migration sequence is `hybrid_ai_implementation_plan.md`.

## Runtime pipeline

```text
Natural-language request
       │
       ▼
AI diagram designer
semantics + visual intent + proposed geometry
       │
       ▼
Hard validation
schema + references + containment + geometry + page bounds
       │
       ├── correctable failure → one AI repair attempt → validate again
       │
       ▼
Hybrid layout
preserve valid AI composition; apply bounded mechanical safeguards
       │
       ▼
Native Visio renderer
editable template shapes + labels + callouts + glued connectors
       │
       ▼
Structural VSDX validation
       │
       ▼
Preview image export
       │
       ▼
Multimodal AI critic
inspect actual drawing for visual and semantic problems
       │
       ├── one valid structured revision → rerender and revalidate
       │
       ▼
Final VSDX + preview + complete provenance artifacts
       │
       ▼
Microsoft Visio acceptance
```

## AI diagram designer

The first AI stage acts as a diagram designer rather than a narrow extractor. It receives the user’s description and returns a structured design containing:

- diagram family and orientation;
- nodes, labels, semantic types, containers, and reference numerals;
- typed and directed relationships;
- grouping and visual hierarchy;
- a composition style;
- preferred node rectangles in page inches;
- optional preferred connector sides;
- a short design rationale retained for auditing.

The model may produce different valid compositions on different runs. Provider generation settings are explicit, and exact JSON equality is not a product requirement.

The model does not create VSDX package XML, choose internal master IDs, or write connector formulas. Those details remain inside tested application code.

## Validation and AI-assisted repair

Visiogen does not treat a schema-valid model response as automatically usable. Code checks the facts it can verify reliably: unique IDs, valid endpoints, supported types, legal containment, positive complete geometry, page bounds, overlap, and child placement inside containers.

If the design fails a correctable check, the model receives concise machine-generated errors together with the original request and its previous design. It gets one opportunity to return a corrected design. A second invalid response fails clearly. The application does not silently pretend a repaired fixture or fallback came from the requested provider.

Semantic ambiguity remains an AI responsibility. Code should not invent missing components, silently merge entities, or change relationship meaning merely to make validation pass.

## Hybrid layout

AI-proposed geometry is now allowed and meaningful. When the geometry is valid, the pipeline preserves it instead of discarding it in favor of Graphviz. Code may make small mechanical adjustments such as shifting the drawing inside margins, growing the page, enforcing minimum readable sizes, or expanding a container around its children.

Graphviz remains available when a model omits geometry or the AI layout cannot be repaired, but it is an explicit fallback candidate rather than the visual authority for every run. Fallback use is recorded in the generation artifacts.

This arrangement separates creative composition from hard geometric safety without requiring deterministic output.

## Visual mapping and native Visio rendering

Semantic types remain separate from native Visio shapes. Several concepts may share a reliable template shape while preserving their different meanings in the structured design. The renderer maps the selected semantics and styles to a hand-authored Visio template containing known-good native objects.

For each design, the renderer copies the correct shapes, applies labels and geometry, creates reference callouts, creates connectors with the requested direction and style, and uses tested dynamic-glue formulas so connectors remain attached when shapes move. The renderer saves a new file and never asks the model to manipulate the VSDX package directly.

## Image-based feedback loop

After the first VSDX is generated, desktop Microsoft Visio exports a preview image on Windows. A multimodal model receives that Visio-exported image, the original request, and the structured design. It reviews visible issues such as weak hierarchy, cramped or excessive spacing, crossings, arrows through unrelated shapes, callout obstruction, poor balance, unreadable labels, and missing or visually misleading relationships. If Visio is unavailable, the visual stage remains explicitly pending; no other VSDX renderer is substituted.

The critic returns a structured approval or revision. In the migration MVP, only one revision pass is permitted. The initial VSDX and preview remain preserved beside the critique and revised output, so the system’s intervention is inspectable rather than hidden.

The image critic can judge the Visio-exported preview, but it cannot by itself prove interactive native behavior. Microsoft Visio remains authoritative for opening without repair, editing objects, moving connector endpoints, and save/close/reopen persistence.

## Provider model

Provider selection is explicit. Codex CLI using `gpt-5.6-sol` is the preferred initial provider because the configured local CLI supports strict structured output and image attachments. Gemini and local OpenAI-compatible models can implement the same design or critique contracts when their capabilities and real acceptance results justify it.

Text design and image critique are separate capabilities. A text-only provider may design a graph but cannot be credited with visual review. Visiogen does not silently replace one provider with another after a failure.

## Provenance and testing

Every real generation stores the source request, exact provider and model, structured responses, validation findings, initial and revised designs, preview images, VSDX files, timing, and checksums. A checked-in fixture is never labeled as provider output.

Fake clients and runners remain useful for unit tests that verify request construction, parsing, retries, and typed failures. They cannot close an AI-quality milestone. AI capability is accepted only through the real production adapter and actual provider.

Because variation is expected, quality is measured with hard invariants and rubrics rather than byte-for-byte output equality. Representative acceptance covers a branching flowchart, a system diagram, and a contained component schematic. Native Windows Visio testing remains a separate final gate.

## Baseline boundaries

The hybrid MVP supports one page and one critique-driven revision. It does not include unbounded autonomous loops, candidate swarms, multi-page document planning, CAD geometry, direct AI-authored ShapeSheet formulas, perfect routing, automatic provider fallback, or patent-office compliance claims.

The result should be described honestly as an AI-designed editable first draft. Its quality must be demonstrated with preserved real-provider artifacts and actual Visio behavior, not inferred from fixtures or structural tests.
