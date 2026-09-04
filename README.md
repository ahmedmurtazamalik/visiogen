# Visiogen

**Current release line:** `0.1.0` experimental release candidate. The document-
analysis path has passed its A8 release evaluation under the recorded autonomous
AI-assisted review policy. See the
[`0.1.0 experimental release record`](docs/releases/0.1.0-experimental.md) for the
supported boundary, measured evidence, and separate generation acceptance gates.

Visiogen is an AI-assisted diagram toolkit with two independent product
directions:

1. **Diagram generation:** turn a natural-language request into an editable,
   native Microsoft Visio `.vsdx` first draft.
2. **Document analysis:** inspect diagrams in PDF or DOCX documents, describe their
   visible semantics, and compare them with related document text.

The public `visiogen generate` command now runs the Generation v2 vertical pipeline:
specification, analysis import, AI construction planning, deterministic compilation,
and native VSDX rendering. Visual diagnostics, iterative editing, comparative
evaluation, and Windows native acceptance remain later gates. Document analysis has completed safe
deterministic PDF/DOCX ingestion, diagram discovery/image preparation, and accepted
evidence-grounded visual observation, semantic reconstruction, faithful textual
description, bounded document-text claim extraction, conservative entity alignment,
and evidence-backed consistency findings. The public `visiogen analyze` pipeline and
CLI are implemented and have passed the controlled A7 PDF/DOCX vertical gate.

The supported generation targets are flowcharts, system and architecture diagrams,
and abstract component or patent-oriented schematics. Visiogen produces editable
first drafts, not CAD models, physically exact reconstructions, or filing-ready
patent drawings.

## Product paths

```text
Generation                         Analysis
text request                       PDF or DOCX
    → validated specification          → safe document decomposition
    → AI construction plan             → diagram discovery
    → deterministic compiler           → visual semantic reconstruction
    → native VSDX rendering            → faithful textual description
    → editable Visio draft             → text/diagram consistency findings
```

The paths share narrowly scoped provider and configuration infrastructure, but
neither depends on the other. Generation work can continue while document analysis
is developed independently.

## Generation architecture

The former Generation v1 hybrid pipeline was:

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

Generation v2 separates what the diagram must communicate from how Visio should
construct it:

```text
natural language / professional specification / analysis bundle
→ validated DiagramSpecification
→ AI-authored VisioConstructionPlan
→ deterministic validation and renderer-neutral compilation
→ native VSDX renderer
→ editable VSDX and provenance bundle
```

G0–G4 are complete, the G5 renderer passes its local structural gate, and the G8
vertical path is wired into the public CLI. G6 visual diagnostics and G7 iterative
editing were not required for the first complete text/specification-to-VSDX path
and remain deferred. Windows Visio lifecycle acceptance and comparative quality
evaluation are still pending. Explicit connectors now use live named-port glue,
Visio-native inward direction vectors, consistent connection-row metadata, and
movement-aware route geometry. The Windows gate checks endpoint movement and rejects
straight-line detours across move, undo, redo, save, and reopen. See the
[Generation v2 implementation plan](docs/plans/active/GENERATION_V2.md),
[native renderer contract](docs/generation/NATIVE_RENDERER_V2.md), and
[pipeline evolution](docs/generation/PIPELINE_EVOLUTION.md).

The historical v1 contract is [`docs/architecture/HYBRID_AI.md`](docs/architecture/HYBRID_AI.md).

## Generate a diagram

Requirements are Python 3.11+, [uv](https://docs.astral.sh/uv/), and an authenticated
Codex CLI. Generation and structural VSDX validation run on Linux. Desktop Microsoft
Visio on Windows remains authoritative for visual and native lifecycle acceptance.

```bash
uv sync --extra dev

uv run visiogen generate \
  --text "Create a left-to-right system where a sensor sends data to a processor and the processor reads and writes memory." \
  --output artifacts/my-run/final.vsdx \
  --artifact-dir artifacts/my-run/evidence
```

While the command runs, it prints elapsed-time stage updates to stderr for
specification, construction planning, compilation, rendering, validation, and
evidence publication. Use `--quiet` to suppress these updates in scripts; the final
VSDX and evidence paths are still printed.

Independent generation commands may run concurrently when every command uses a
different output path and evidence directory. Shell variables are local to one
terminal, so either define a run-directory variable separately in every terminal or
use explicit paths. Visiogen rejects attempts to create a new top-level filesystem
directory, which commonly indicates that an unset variable turned a relative path
into a path such as `/08-event-driven/final.vsdx`. If specification or construction
validation exhausts its repair attempt, both model responses and the final validation
finding remain in that run's evidence directory.

Generation defaults to 300 seconds per model call. Complex concurrent runs can spend
longer waiting on the provider; use `--timeout 600` and limit initial batches to two
simultaneous commands when testing large diagrams.

Generation v2 also accepts a reviewed, strict JSON or YAML professional
specification with `--spec-file`. Natural-language input is first converted to the
same validated specification and the result is retained in the evidence bundle.
See the [DiagramSpecification contract](docs/generation/DIAGRAM_SPECIFICATION.md).

A completed analysis evidence bundle can be projected into a reviewable draft
specification with `--analysis-bundle --stop-after-specification`. Ambiguous and
unsupported observations remain explicit review items. See the
[analysis import contract](docs/generation/ANALYSIS_IMPORT.md).

The default provider/model is the locally authenticated Codex CLI using
`gpt-5.6-sol`. Every v2 run preserves the exact request, logical and transport
prompts, raw structured responses, validated specification and construction plan,
compiler IR, final VSDX, timing, provider/model identity, and SHA-256 checksums.

The adapter uses an ephemeral read-only workspace, ignores Codex user config/rules, gives model-run shell commands no inherited environment, and passes the Codex process only a small runtime/auth allowlist. It is nevertheless an agentic local CLI with read access under Codex's sandbox policy. Treat diagram requests as trusted local input; adversarial third-party documents containing embedded instructions require stronger OS/container isolation or a non-agentic API adapter.

The v2 CLI does not yet perform preview-based visual editing. The compatibility
flag `--no-critique` is accepted but has no additional effect; the manifest records
that visual diagnostics and editing were not performed.

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
dense tiled images, annotations/callouts, and explicit ambiguity. See
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

The command prints elapsed-time progress to stderr while it extracts the document,
discovers and prepares candidates, runs semantic and claim stages, checks
consistency, and publishes artifacts. Each selected diagram is shown with its
candidate number and completed model-call count. Use `--quiet` to suppress progress
updates in scripts.

It publishes an accessible report separately from the private evidence bundle and
returns a distinct exit code for partial candidate failure. Fresh PDF and DOCX
sources have passed the clean-source, real-`gpt-5.6-sol`, hash-bound vertical gate;
see [`docs/acceptance/A7_VERTICAL_PIPELINE.md`](docs/acceptance/A7_VERTICAL_PIPELINE.md).
The complete seven-case A8 corpus, deterministic hardening gate, and checksum-bound
release evaluation have also passed. The review was completed as two isolated
AI-assisted passes under explicit user authorization, not as two human signatures;
see [`docs/acceptance/A8_AI_ASSISTED_ACCEPTANCE.md`](docs/acceptance/A8_AI_ASSISTED_ACCEPTANCE.md).
The current candidate boundary accepts portable DOCX extraction only; rendered Word
or LibreOffice page modes are not yet supported. See
[`docs/analysis/A8_SUPPORTED_SCOPE.md`](docs/analysis/A8_SUPPORTED_SCOPE.md).

A post-implementation completeness audit removed skipped tests and closed additional
A0–A7 contract, safety, evidence, scope, and failure-provenance gaps. The exact audit
scope and distinction between historical provider evidence and new deterministic
coverage are recorded in
[`docs/acceptance/A0_A7_COMPLETENESS_AUDIT.md`](docs/acceptance/A0_A7_COMPLETENESS_AUDIT.md).

## Development

```bash
uv run pytest -q
uv run visiogen --help
uv build
```

Fake provider runners are used only for low-level schema, process, retry, and orchestration tests. They are not AI-quality evidence. Real-provider acceptance artifacts must come through the production adapter and retain their prompts and responses.

Every release-quality analysis change starts from a named clean Git checkpoint and
produces a new immutable preflight, corpus, hardening, review, and decision lineage.
The repeatable procedure is documented in
[`docs/development/RELEASE_CHECKPOINTS.md`](docs/development/RELEASE_CHECKPOINTS.md).

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
