# Visiogen

Visiogen is an AI-assisted diagram toolkit with two independent product
directions:

1. **Diagram generation:** turn a natural-language request into an editable,
   native Microsoft Visio `.vsdx` first draft.
2. **Document analysis:** inspect diagrams in PDF or DOCX documents, describe their
   visible semantics, and compare them with related document text.

The generation pipeline is implemented. Document analysis has completed safe
deterministic PDF/DOCX ingestion, diagram discovery/image preparation, and accepted
evidence-grounded visual observation, semantic reconstruction, faithful textual
description, bounded document-text claim extraction, conservative entity alignment,
and evidence-backed consistency findings. Public pipeline and CLI integration are the
next analysis phase; the `visiogen analyze` command is not implemented yet.

The supported generation targets are flowcharts, system and architecture diagrams,
and abstract component or patent-oriented schematics. Visiogen produces editable
first drafts, not CAD models, physically exact reconstructions, or filing-ready
patent drawings.

## Product paths

```text
Generation                         Analysis
text request                       PDF or DOCX
    → AI diagram design                → safe document decomposition
    → hard validation                  → diagram discovery
    → native VSDX rendering            → visual semantic reconstruction
    → image-based critique             → faithful textual description
    → editable Visio draft             → text/diagram consistency findings
```

The paths share narrowly scoped provider and configuration infrastructure, but
neither depends on the other. Generation work can continue while document analysis
is developed independently.

## Hybrid-AI architecture

Visiogen now uses a hybrid design pipeline rather than limiting the LLM to semantic extraction:

```text
text request
→ AI semantic + visual design with proposed geometry
→ hard schema/reference/containment/geometry validation
→ at most one AI repair
→ native VSDX rendering
→ real preview image export
→ multimodal AI visual critique
→ at most one structured revision and rerender
→ final VSDX, preview, and provenance bundle
```

Output is intentionally allowed to vary between runs. Code remains authoritative for hard invariants and VSDX package safety; AI contributes semantic judgment, hierarchy, composition, geometry, and image-grounded improvement. The model never authors VSDX XML or ShapeSheet formulas directly.

The authoritative generation contract is
[`docs/architecture/HYBRID_AI.md`](docs/architecture/HYBRID_AI.md).

## Generate a diagram

Requirements are Python 3.11+, [uv](https://docs.astral.sh/uv/), and an authenticated Codex CLI. The complete visual-critique path additionally requires Windows and desktop Microsoft Visio, which is used both for preview export and authoritative native acceptance. Linux can run design/render with `--no-critique`, but that does not close visual acceptance.

```bash
uv sync --extra dev

uv run visiogen generate \
  --text "Create a left-to-right system where a sensor sends data to a processor and the processor reads and writes memory." \
  --output artifacts/my-run/final.vsdx \
  --artifact-dir artifacts/my-run/evidence
```

The default provider/model is the locally authenticated Codex CLI using `gpt-5.6-sol`. Every run preserves the exact request, logical system/user prompts, exact transport prompts sent after adapter wrapping, raw structured responses, validated designs, initial and revised VSDX files, preview images, timing, provider/model identity, and final SHA-256 checksum.

The adapter uses an ephemeral read-only workspace, ignores Codex user config/rules, gives model-run shell commands no inherited environment, and passes the Codex process only a small runtime/auth allowlist. It is nevertheless an agentic local CLI with read access under Codex's sandbox policy. Treat diagram requests as trusted local input; adversarial third-party documents containing embedded instructions require stronger OS/container isolation or a non-agentic API adapter.

Visual critique is enabled by default. It can be explicitly skipped with `--no-critique`; the manifest records that it did not occur.

```bash
uv run visiogen generate \
  --input-file request.txt \
  --output artifacts/my-run/final.vsdx \
  --artifact-dir artifacts/my-run/evidence \
  --no-critique
```

## Analyze a document

The analysis workflow is:

```text
PDF or DOCX
→ discover diagram candidates
→ extract visible objects, labels, containers, connectors, and directions
→ preserve image-region and document-text evidence
→ generate a structured diagram model and faithful description
→ independently extract claims from related prose
→ report evidence-backed inconsistencies and uncertainty
```

This work does not require Microsoft Visio and does not call the generation
pipeline. The implementation plan, schemas, security model, fixture strategy, and
acceptance gates are documented in
[`docs/plans/active/DOCUMENT_ANALYSIS.md`](docs/plans/active/DOCUMENT_ANALYSIS.md).

The A3 visual-semantics core now has a clean real-provider acceptance record covering
objects, labels, visible reference numerals, relationships, direction, grouping,
dense tiled images, and explicit ambiguity. See
[`docs/acceptance/A3_VISUAL_SEMANTICS.md`](docs/acceptance/A3_VISUAL_SEMANTICS.md).

A4 deterministically turns that validated semantic model into traceable JSON and
accessible Markdown without another model call. Its six-case acceptance record is
[`docs/acceptance/A4_FAITHFUL_DESCRIPTION.md`](docs/acceptance/A4_FAITHFUL_DESCRIPTION.md).

A6 compares the diagram reconstruction with independently extracted prose claims.
Its 39-case deterministic acceptance matrix covers contradictions, consistency, and
ambiguity across all planned categories with evidence-complete findings and strict
omission safeguards. See
[`docs/acceptance/A6_CONSISTENCY.md`](docs/acceptance/A6_CONSISTENCY.md).

The A7 public interface is available:

```bash
uv run visiogen analyze \
  --input design-spec.pdf \
  --output artifacts/review/report.md \
  --artifact-dir artifacts/review/evidence \
  --model gpt-5.6-sol
```

It publishes an accessible report separately from the private evidence bundle and
returns a distinct exit code for partial candidate failure. Fresh PDF and DOCX
sources have passed the clean-source, real-`gpt-5.6-sol`, hash-bound vertical gate;
see [`docs/acceptance/A7_VERTICAL_PIPELINE.md`](docs/acceptance/A7_VERTICAL_PIPELINE.md).
Broader held-out quality and DOCX rendering scope remain Phase A8.

## Development

```bash
uv run pytest -q
uv run visiogen --help
uv build
```

Fake provider runners are used only for low-level schema, process, retry, and orchestration tests. They are not AI-quality evidence. Real-provider acceptance artifacts must come through the production adapter and retain their prompts and responses.

The repository is divided into generation-owned and analysis-owned paths so two
contributors can work concurrently. See
[`docs/development/WORKSTREAMS.md`](docs/development/WORKSTREAMS.md) for ownership,
import-direction, worktree, and integration rules.

The documentation index is [`docs/README.md`](docs/README.md). Current architecture
and active plans are separated from historical plans and milestone records.

## Existing milestone evidence

- [`docs/acceptance/archive/M4_EXTRACTION.md`](docs/acceptance/archive/M4_EXTRACTION.md)
  records actual Codex, Gemini, and local-Qwen extraction runs.
- [`docs/acceptance/archive/M5_LAYOUT.md`](docs/acceptance/archive/M5_LAYOUT.md)
  records the former deterministic Graphviz/fallback baseline.
- [`docs/acceptance/archive/M6_RENDERING.md`](docs/acceptance/archive/M6_RENDERING.md)
  records native template rendering and its Microsoft Visio acceptance status.

Linux ZIP/XML validation is structural evidence only. Microsoft Visio is the sole preview/export and native-behavior authority for visual critique, repair prompts, editability, connector movement, and save/close/reopen behavior.

## Windows hybrid acceptance

The final three-case corpus and native Visio lifecycle gate are automated by:

```powershell
.\scripts\run_windows_hybrid_corpus.ps1 `
  -OutputDirectory "C:\VisiogenAcceptance\hybrid-$(git rev-parse --short HEAD)" `
  -Model "gpt-5.6-sol" `
  -Visible
```

The output path must not already exist and must be outside the source checkout. The
runner requires clean immutable source, performs real Visio-exported visual
critique, then opens, moves, saves, closes, and reopens each final VSDX through
desktop Microsoft Visio. Its report remains pending until the documented human
visual review is completed. See
[`docs/acceptance/WINDOWS_VISIO.md`](docs/acceptance/WINDOWS_VISIO.md) for
prerequisites, exact evidence, manual visual checks, and failure handling.

## Template masters

The renderer currently retains the canonical template's complete master catalog. The template contains 19 master definitions plus `masters.xml`; a representative basic-system drawing references only Dynamic connector, Database, Rounded Rectangle, and Circle. The other 15 definitions are package bloat, not page dependencies. Pruning is deferred until coordinated catalog, relationship, content-type, and part cleanup has dedicated tests and the pruned result passes Microsoft Visio open/edit/save/reopen acceptance.
