# Visiogen Text-to-Visio Baseline Implementation Plan

> **Historical execution plan.** The geometry-free, deterministic-output architecture in this document was superseded on 2026-08-20 by `docs/HYBRID_AI_ARCHITECTURE.md` and `hybrid_ai_implementation_plan.md`. Preserve completed milestone evidence, but follow the hybrid plan for all new implementation.

> **For Hermes:** Execute this plan task-by-task with strict test-driven development. Do not advance past a milestone gate until its acceptance criteria pass. Use fresh implementation/review context for each milestone, and preserve all evidence under `artifacts/` or the milestone commit.

**Goal:** Build a Python CLI and library that convert supported natural-language descriptions into validated, editable Microsoft Visio `.vsdx` first drafts for flowcharts, system block diagrams, and abstract patent-oriented component schematics.

**Architecture:** The implementation is a staged pipeline: provider-specific structured extraction → provider-neutral normalization → deterministic layout → semantic-to-visual mapping → template-based VSDX rendering → structural and real-Visio validation. `DiagramGraph` is the authoritative boundary contract. LLM providers never emit geometry, and the renderer never interprets prose.

**Tech Stack:** Python 3.11+, `uv`, Pydantic 2, pytest/pytest-cov, NetworkX, Graphviz `dot`, `vsdx`, an OpenAI-compatible HTTP client for local Qwen, `google-genai` for Gemini, standard-library ZIP/XML validation, PowerShell + Visio COM for Windows acceptance.

---

## 1. Execution Rules

1. Work from `/home/murtaza/Murtaza/Visiogen` and use `project/` as the application repository root.
2. Use `python3` and a `uv`-managed virtual environment; never install into the PEP 668 system environment.
3. Follow vertical TDD for production behavior: write one focused test, run it and confirm the expected failure, add the minimum implementation, run the focused test, then run the relevant test module/suite.
4. Do not create extraction, layout, and rendering in one module. Enforce the dependency direction:
   `cli/pipeline → providers + normalization + layouts + mapper + renderer + validation`.
5. Do not guess `vsdx` package APIs. M2 is an explicit spike; record only APIs proven against the pinned installed version and real Visio.
6. Do not silently fall back between Qwen and Gemini. Provider choice and cloud transmission must be explicit.
7. Do not commit model files, API keys, generated bulk artifacts, virtual environments, or local debug output.
8. Use small dependency-ordered commits with plain messages such as `Add graph validation` rather than conventional prefixes.
9. At Windows gates, stop and provide the exact commit, artifact names, and checklist. Do not claim success without a real Visio report.
10. Preserve the baseline scope. Defer multi-page documents, arbitrary stencils, CAD/physical geometry, perfect connector routing, and patent-office compliance.

## 2. Milestone and Dependency Map

```text
M0 scaffold and Git checkpoint
 ├─ M1 graph contract/normalization
 └─ M2 VSDX feasibility spike ── Windows gate (blocks renderer work)
       └─ M3 template vocabulary + shape mapping

M1 ──┬─ M4 fixture corpus + provider-neutral extraction
     └─ M5 deterministic layout

M2 + M3 + M5 ── M6 renderer
M4 + M5 + M6 ── M7 pipeline/CLI/debug artifacts
M6 + M7 ── M8 structural + Windows validation
M8 ── M9 end-to-end baseline acceptance/release docs
```

M1, M4, and M5 can proceed while Windows work is pending. M6 must not begin until M2 proves editable shapes and glued connectors in Microsoft Visio.

---

## 3. M0 — Stage the Repository, Then Establish Git

### Task M0.1: Create only the agreed scaffold

**Objective:** Establish the package/test/document shape without implementing behavior.

**Files to create:**

```text
project/
  pyproject.toml
  README.md
  .gitignore
  src/visiogen/__init__.py
  src/visiogen/models.py
  src/visiogen/config.py
  src/visiogen/extractor.py
  src/visiogen/normalization.py
  src/visiogen/layout.py
  src/visiogen/shape_mapper.py
  src/visiogen/renderer.py
  src/visiogen/validation.py
  src/visiogen/pipeline.py
  src/visiogen/cli.py
  src/visiogen/providers/__init__.py
  src/visiogen/providers/base.py
  src/visiogen/providers/local_qwen.py
  src/visiogen/providers/gemini.py
  src/visiogen/layouts/__init__.py
  src/visiogen/layouts/graphviz_layout.py
  src/visiogen/layouts/fallback_layered.py
  templates/TEMPLATE.md
  scripts/validate_in_visio.ps1
  tests/conftest.py
  tests/fixtures/text/.gitkeep
  tests/fixtures/graphs/.gitkeep
```

**Implementation notes:**
- `pyproject.toml` defines package `visiogen`, `src` layout, Python `>=3.11`, runtime dependencies, test dependencies, and a `visiogen = "visiogen.cli:main"` script.
- Keep dependency versions constrained but do not lock the `vsdx` version until M2 identifies the working release.
- `.gitignore` covers `.venv/`, Python caches, coverage, `.env*` except `.env.example`, local GGUF/model directories, and `artifacts/*` except intentional acceptance fixtures/reports.
- Placeholder modules contain docstrings only; no speculative APIs.

**Verification:**

```bash
cd /home/murtaza/Murtaza/Visiogen/project
uv sync
uv run python3 -c "import visiogen"
uv run pytest -q
uv run visiogen --help
```

Expected: import succeeds, empty test run has no collection/import errors, CLI help exits 0.

### Task M0.2: Pause for repository connection

After the scaffold and verification, present `git status --short` and stop so the user can connect/confirm the Git remote and create the initial commit according to their staged-repository preference. Do not implement M1 before this checkpoint.

**Suggested commit:** `Create Visiogen project scaffold`

**Gate M0:** package import and CLI help work from a clean environment; repository ownership/remote is confirmed.

---

## 4. M1 — Authoritative Graph Contract and Normalization

### Task M1.1: Define graph models

**Files:**
- Modify: `project/src/visiogen/models.py`
- Create: `project/tests/test_models.py`

**Public contract:**
- Literals: `DiagramType`, `Orientation`, `NodeType`, `RelationType`, `DirectionType`, `LineStyle` exactly as listed in the source implementation plan.
- Models: `DiagramNode`, `DiagramEdge`, `DiagramGraph`.
- Geometry is optional only in the canonical graph because the same type crosses pre/post-layout boundaries.

**TDD slices:**
1. Minimal valid graph parses and round-trips through `model_dump_json()`/`model_validate_json()`.
2. Unsupported enum values fail with useful Pydantic errors.
3. Pre-layout graph can omit all geometry.
4. Post-layout graph can retain positive float geometry.
5. Add a helper/property that detects whether any geometry was supplied; do not conflate this with full layout validation.

**Commands:**

```bash
uv run pytest tests/test_models.py -q
uv run pytest -q
```

**Suggested commit:** `Add diagram graph models`

### Task M1.2: Separate provider DTOs from canonical models

**Files:**
- Modify: `project/src/visiogen/extractor.py`
- Create/modify: `project/tests/test_extractors.py`

Define extraction-only Pydantic DTOs that do not declare `x`, `y`, `width`, or `height`. Configure them to reject extra fields, so model-produced geometry is a schema error rather than ignored input. Add a deterministic conversion function to `DiagramGraph`.

**TDD slices:** accepted semantic DTO; geometry rejected; missing edge ID accepted only in DTO; canonical edge IDs assigned later by normalization.

**Suggested commit:** `Separate extraction models from layout geometry`

### Task M1.3: Normalize and validate graph references

**Files:**
- Modify: `project/src/visiogen/normalization.py`
- Create: `project/tests/test_normalization.py`

Define explicit exception types, preferably under the same module initially:
- `GraphNormalizationError`
- structured error details carrying field/entity context.

Implement `normalize_graph(graph: DiagramGraph) -> DiagramGraph` as a pure function that returns a new canonical graph and never mutates caller data.

**TDD slices, one at a time:**
1. Reject duplicate node IDs.
2. Reject duplicate non-empty edge IDs.
3. Assign missing edge IDs deterministically in stable input order (`e1`, `e2`, avoiding collisions).
4. Reject dangling source and target IDs.
5. Reject a missing `parent_id` target.
6. Reject parents whose semantic type is not `housing` or `subsystem`.
7. Reject self-parent and containment cycles.
8. Reject depth greater than one container level.
9. Reject duplicate reference numerals after trimming surrounding whitespace.
10. Preserve input node/edge order and all semantic labels.
11. Reject pre-layout geometry at the extraction-to-normalization boundary through a dedicated validation entry point.

Do not invent domain components, labels, reference numbers, or relationships. If diagram-type inference is retained, implement it as an explicit helper taking the source text plus DTO and cover its narrow keyword rule with tests; otherwise require providers to supply a valid type. Do not hide inference inside general normalization.

**Fixtures:**
- Create: `tests/fixtures/graphs/linear_flow.json`
- Create: `tests/fixtures/graphs/basic_system.json`
- Create: `tests/fixtures/graphs/nested_subsystem.json`

**Suggested commit:** `Add graph normalization and reference validation`

**Gate M1:** model and normalization tests cover every contract rule; round-trip JSON preserves semantics; extraction DTOs cannot contain geometry.

---

## 5. M2 — VSDX Feasibility Spike (Critical Stop/Go Gate)

### Task M2.1: Author the minimal Windows template

**Windows-owned file:**
- Create: `project/templates/template.vsdx`
- Modify: `project/templates/TEMPLATE.md`

Create one palette page containing known-good objects with unique stable marker text:
- `__template_process__`
- `__template_component_rectangle__`
- `__template_subsystem_container__`
- `__template_reference_callout__`
- `__template_connector__`

Document template page name, marker, intended use, and any required shape/master property. One editor owns binary template changes at a time.

**Suggested commit:** `Add minimal Visio template`

### Task M2.2: Prove the Python library operations on Ubuntu

**Files:**
- Modify: `project/src/visiogen/renderer.py`
- Create: `project/tests/test_renderer_spike.py`
- Create: `project/artifacts/spike/` outputs locally (ignored until explicitly approved)

Before writing a wrapper, inspect the installed `vsdx` package and make a throwaway script/test prove these exact operations:
1. Load `templates/template.vsdx`.
2. Find palette shapes by stable marker text.
3. Copy at least two endpoint shapes without altering the palette originals.
4. Replace visible text.
5. Set center position and dimensions.
6. Copy/create one connector.
7. Glue connector endpoints using the actual library/package API.
8. Save to a different path.
9. Re-open the saved package with the same library.

Convert successful exploratory code into the smallest renderer helpers with integration tests. Record installed package version and verified API details in `TEMPLATE.md` and comments. If public APIs cannot glue connectors, investigate package XML only as a documented fallback; do not silently build a broad custom VSDX writer.

**Ubuntu verification:**

```bash
uv run pytest tests/test_renderer_spike.py -q
uv run python3 -m zipfile -t artifacts/spike/minimal.vsdx
```

### Task M2.3: Real Visio acceptance

On Windows, pull the exact commit and open `artifacts/spike/minimal.vsdx` in Microsoft Visio.

**Required evidence:**
- no repair prompt;
- copied shapes have editable labels and geometry;
- moving each endpoint keeps the connector attached;
- file can be edited, saved, closed, and reopened;
- record Visio version, Git commit, artifact checksum, pass/fail notes.

**Decision:**
- **Pass:** pin the exact `vsdx` version and proceed.
- **Fail:** stop renderer implementation, isolate whether copying, relationships, or connector glue failed, and revise library/template strategy. M6 remains blocked.

**Suggested commit after pass:** `Prove editable Visio rendering spike`

**Gate M2:** real Visio proves no repair prompt and genuine connector glue.

---

## 6. M3 — Complete Template Vocabulary and Visual Mapping

### Task M3.1: Expand and document the template palette

**Files:**
- Modify on Windows: `project/templates/template.vsdx`
- Modify: `project/templates/TEMPLATE.md`

Add the baseline visual markers listed in the source plan. Keep roughly 15–20 visual templates; reuse geometry where semantics do not justify a distinct shape. Include a palette inventory table with marker, semantic users, default width/height, container capability, and validation status.

Run a Windows open/save smoke test after expansion before changing mapper code.

**Suggested commit:** `Expand the Visio template palette`

### Task M3.2: Implement node and edge mapping

**Files:**
- Modify: `project/src/visiogen/shape_mapper.py`
- Create: `project/tests/test_shape_mapper.py`

Use immutable mapping data and typed return models such as `NodeVisualSpec` and `EdgeVisualSpec`. Cover every `NodeType`, `RelationType`, direction, and explicit line style. Explicit graph line style wins over a relation default; relation determines default arrow/weight behavior; direction determines begin/end arrows.

**TDD slices:**
- every node semantic type resolves;
- known semantic aliases reuse intended visual template;
- every relation/direction combination is deterministic;
- dotted/dashed override is preserved;
- missing template inventory key raises a clear `ShapeMappingError`;
- coverage test fails whenever a new literal is added without a mapping.

**Suggested commit:** `Add deterministic visual mapping`

**Gate M3:** template opens in Visio; all semantic variants map to documented markers with no silent fallback.

---

## 7. M4 — Fixture Corpus and Provider-Neutral Extraction

### Task M4.1: Create reviewed semantic fixtures

**Files:**
- Add 10 prompt files under `project/tests/fixtures/text/` matching the acceptance set in the source plan.
- Add reviewed expected graphs under `project/tests/fixtures/graphs/expected/`.

For ambiguous text, choose and document one baseline behavior before provider work: recommended default is a clear `NoDiagramContentError` rather than manufacturing a node. Golden graphs compare semantics while ignoring generated edge IDs only where omission is permitted.

**Suggested commit:** `Add reviewed extraction fixtures`

### Task M4.2: Define provider protocol, errors, and shared prompt

**Files:**
- Modify: `project/src/visiogen/providers/base.py`
- Modify: `project/src/visiogen/extractor.py`
- Create/modify: `project/tests/test_extractors.py`

Define:

```python
class DiagramExtractor(Protocol):
    def extract(self, text: str) -> DiagramGraph: ...
```

Also define `ProviderError`, `ExtractionValidationError`, a shared system prompt builder, schema-repair prompt builder, and orchestration that permits exactly one repair retry. Inject the transport/model call as a seam so tests use deterministic fake responses, not network mocking at every layer.

**TDD slices:** valid first response; invalid then repaired response; two invalid responses fail; no geometry accepted; timing/request ID metadata excludes prompt secrets/keys; empty text fails before provider invocation.

**Suggested commit:** `Add provider-neutral extraction workflow`

### Task M4.3: Implement explicit configuration

**Files:**
- Modify: `project/src/visiogen/config.py`
- Create: `project/tests/test_config.py`
- Create: `project/.env.example`

Parse provider, local base URL/model, Gemini model/key, timeout, and debug policy. No import-time environment reads; expose `Settings.from_env()` and allow explicit constructor values in tests. Validate only the credentials/config required by the selected provider.

**Suggested commit:** `Add explicit provider configuration`

### Task M4.4: Implement local Qwen adapter

**Files:**
- Modify: `project/src/visiogen/providers/local_qwen.py`
- Create: `project/tests/providers/test_local_qwen.py`

Target OpenAI-compatible `/v1/chat/completions` through a small HTTP/client adapter. Send schema-constrained or JSON-only output as supported by the endpoint, low-variance generation settings, configured timeout/model, and no fallback. Convert transport, HTTP, malformed JSON, and schema failures into typed errors while retaining safe request metadata.

Tests use a fake client and assert request construction plus error translation. Live tests use `@pytest.mark.integration` and require explicit environment enablement.

**Suggested commit:** `Add local Qwen extraction provider`

### Task M4.5: Implement Gemini adapter

**Files:**
- Modify: `project/src/visiogen/providers/gemini.py`
- Create: `project/tests/providers/test_gemini.py`

Use `google-genai` structured output against the extraction DTO schema. Model comes from configuration. Tests use an injected fake SDK client. Never log or serialize `GEMINI_API_KEY`.

**Suggested commit:** `Add Gemini extraction provider`

### Task M4.6: Run fixture contract comparisons

Add parametrized mocked provider tests proving both adapters feed the same canonical validation path. Add optional live scripts/tests that write actual outputs under `artifacts/provider-evaluation/<provider>/`, never overwrite reviewed expected fixtures, and produce a small semantic mismatch report.

**Gate M4:** both providers pass the same mocked contract; 5 flow + 5 system/component fixtures validate; live tests are opt-in and normal CI is offline.

---

## 8. M5 — Deterministic Layout

### Task M5.1: Define positioned output contract and sizing

**Files:**
- Modify: `project/src/visiogen/layout.py`
- Create: `project/tests/test_layout.py`

Define `PageGeometry`, `LayoutResult`, and `LayoutError`. The result contains a new graph with center-based inches in Visio bottom-left coordinates plus page dimensions. Add deterministic label wrapping and min/max size rules keyed by visual family.

Test positive dimensions, input immutability, stable output, bounded long-label sizing, and reserved reference-number space.

**Suggested commit:** `Define deterministic layout contract`

### Task M5.2: Generate and parse Graphviz layout

**Files:**
- Modify: `project/src/visiogen/layouts/graphviz_layout.py`
- Create: `project/tests/test_graphviz_layout.py`
- Add DOT snapshots under `project/tests/fixtures/dot/`

Generate DOT with escaped labels/IDs, fixed graph/node/rank spacing, rank direction by diagram type/orientation, clusters for one-level containers, and edge weighting that does not treat associations as process flow. Invoke `dot -Tplain` through an injected command runner; parse its output robustly and convert top-origin Graphviz coordinates exactly once into Visio bottom-left inches.

Test missing executable, nonzero exit, malformed output, quoted IDs, both orientations, clusters, and deterministic snapshots.

**Suggested commit:** `Add Graphviz layout strategy`

### Task M5.3: Implement deterministic fallback

**Files:**
- Modify: `project/src/visiogen/layouts/fallback_layered.py`
- Create: `project/tests/test_fallback_layout.py`

Use stable topological/layer ordering for directed graphs and stable input order for cycles/undirected components. Place containers first, then children on an internal grid. Grow page bounds with margins. Quality may be lower than Graphviz but geometry must remain valid.

**Suggested commit:** `Add fallback layered layout`

### Task M5.4: Add geometry acceptance tests

Create shared assertions for:
- positive geometry;
- ordinary node non-overlap with tolerance;
- child bounding boxes inside parent content bounds;
- all nodes within page bounds;
- same JSON produces byte-equivalent laid-out JSON;
- representative 25-element system fits a grown page.

**Gate M5:** Graphviz and fallback pass geometry invariants for all golden graphs.

---

## 9. M6 — Template-Based Renderer

**Prerequisite:** M2 and M3 are passed and the exact `vsdx` API/version is pinned.

### Task M6.1: Build template inventory and output-page setup

**Files:**
- Modify: `project/src/visiogen/renderer.py`
- Modify: `project/tests/test_renderer.py`

Implement read-only template loading, marker discovery with duplicate/missing-marker errors, and the proven output-page strategy. Never save over the canonical template. Tests copy the template to temporary paths and assert the source checksum is unchanged.

### Task M6.2: Render containers and ordinary nodes

TDD slices: geometry required; containers rendered before children; correct marker copied; text remains editable; dimensions/centers match layout; palette objects removed or isolated per the proven strategy; output page size is set.

### Task M6.3: Render reference numerals/callouts

Use the documented callout template. Preserve explicit numbers as strings. Establish a deterministic anchor/offset rule and make automatic numbering a separate explicit pipeline option, off by default.

### Task M6.4: Render and glue connectors

Create a node-ID-to-Visio-shape map. For each edge, copy/create the proven connector, glue both endpoints, apply begin/end arrows, line style/weight, and editable edge label. Fail on missing endpoints rather than emitting a floating connector.

### Task M6.5: Renderer fixture smoke tests

Render at least:
- `linear_flow.json`;
- `basic_system.json`;
- `headphone.json` with housing, references, and typed links.

Verify source template unchanged, output ZIP/XML readable, expected labels present, approximate shapes/connectors counts match, and saved package reopens through `vsdx`.

**Suggested commits:**
- `Add template inventory and node rendering`
- `Add reference callout rendering`
- `Add glued connector rendering`
- `Add renderer fixture coverage`

**Gate M6:** all three fixtures produce structurally valid packages; Windows confirms labels/editability/glue before pipeline integration is considered complete.

---

## 10. M7 — Pipeline, CLI, and Debug Artifacts

### Task M7.1: Compose the public pipeline

**Files:**
- Modify: `project/src/visiogen/pipeline.py`
- Create: `project/tests/test_pipeline.py`

Implement:

```python
def generate_vsdx(
    text: str,
    output_path: str,
    provider: str,
    *,
    debug_dir: str | None = None,
) -> None: ...
```

Inject providers/layout/renderer in internal orchestration for tests. Write debug stages atomically after each successful boundary:
`01-extracted.json`, `02-normalized.json`, `03-laid-out.json`, `layout.dot` when Graphviz is used, and `pipeline.log`. Keep earlier artifacts if a later stage fails.

TDD slices: successful call order; provider failure preserves available diagnostics; normalization failure blocks layout; layout failure blocks renderer; output parent handling; no canonical template mutation.

**Suggested commit:** `Compose the generation pipeline`

### Task M7.2: Implement CLI commands

**Files:**
- Modify: `project/src/visiogen/cli.py`
- Create: `project/tests/test_cli.py`

Commands:
- `visiogen generate --provider local|gemini (--text TEXT | --input-file PATH) --output PATH [--debug-dir PATH]`
- `visiogen render-graph --graph PATH --output PATH [--debug-dir PATH]`
- `visiogen validate PATH [--json-report PATH]`

Make `--text` and `--input-file` mutually exclusive. Return stable nonzero exit codes for input/config, provider/extraction, graph/layout, rendering, and validation failures. Human errors go to stderr without tracebacks by default; add `--verbose` for diagnostics.

**Suggested commit:** `Add Visiogen command line interface`

### Task M7.3: Add saved-graph replay

Prove `render-graph` uses normalization/layout/mapping/rendering without constructing an LLM client or requiring API configuration. This is the primary renderer/layout debugging path.

**Gate M7:** the documented examples work; provider is explicit in logs; saved JSON renders fully offline.

---

## 11. M8 — Cross-Platform Validation Harness

### Task M8.1: Implement Ubuntu package validation

**Files:**
- Modify: `project/src/visiogen/validation.py`
- Create: `project/tests/test_validation.py`
- Add intentionally broken fixture packages under `project/tests/fixtures/vsdx/` only if compact and legally safe.

Validate without relying solely on `vsdx`:
1. readable ZIP and no duplicate/unsafe entries;
2. `[Content_Types].xml`, root relationships, document, page index, and at least one page exist;
3. every XML part parses;
4. relationship targets referenced by required parts exist;
5. package contains expected labels/count ranges when supplied;
6. return a structured `ValidationReport` with errors, warnings, and checked facts.

**Suggested commit:** `Add structural VSDX validation`

### Task M8.2: Implement Windows Visio validation helper

**File:** `project/scripts/validate_in_visio.ps1`

Parameters: artifact directory/glob, output report path, optional preview directory, expected Git commit. Through Visio COM where available: open each file, capture document/page/shape counts, optionally export preview, close without modifying original, and emit JSON. Detect Visio absence/COM/open failure clearly. Do not attempt to dismiss repair/security dialogs automatically.

Add `project/scripts/README.md` with an interactive checklist for repair prompts, label visibility, containment, arrows, connector labels, endpoint movement/glue, edit/save/reopen, and report attachment.

**Suggested commit:** `Add Windows Visio validation helper`

### Task M8.3: Run exact-commit cross-platform acceptance

Generate the three renderer fixtures plus the full acceptance set from reviewed JSON on Ubuntu. Record SHA-256 checksums using real commands. On Windows, validate those exact files from the exact commit and return the machine-readable report plus manual checklist results.

**Gate M8:** every release artifact passes Ubuntu checks and real Visio open/edit/save; no repair prompt; connector movement passes.

---

## 12. M9 — End-to-End Baseline Acceptance and Documentation

### Task M9.1: Run all 10 text scenarios

For each fixture, run both mocked/reviewed extraction and at least one explicitly selected live provider where credentials/runtime are available. Produce:
- extracted, normalized, and laid-out JSON;
- DOT when applicable;
- VSDX;
- Ubuntu validation report;
- reviewed semantic result;
- Windows report for the release acceptance subset.

Do not alter golden expectations merely to match a provider. Classify mismatches as provider, normalization, layout, rendering, or expectation defects.

### Task M9.2: Benchmark local Qwen deliberately

Test the configured Qwen 3.5 9B GGUF quantization(s) at conservative context (start 8K) on the same fixture set. Record model filename/hash, llama.cpp command/config, CPU/RAM context, latency, schema-valid rate, repair rate, and semantic pass rate. Do not make a quantization the default until evidence supports it.

### Task M9.3: Complete user and contributor documentation

**Files:**
- Modify: `project/README.md`
- Modify: `project/templates/TEMPLATE.md`
- Create: `project/docs/architecture.md`
- Create: `project/docs/validation.md`
- Create: `project/docs/limitations.md`

Document install, Graphviz, local llama.cpp setup, Gemini setup, explicit privacy/provider behavior, CLI/API examples, debug artifacts, template-editing process, testing markers, Windows acceptance, supported 5–25 element scope, and all non-goals. Never claim filing readiness or patent-office compliance.

### Task M9.4: Final quality gate

Run from a clean checkout/environment:

```bash
uv sync --frozen
uv run pytest -q
uv run pytest --cov=visiogen --cov-report=term-missing
uv run visiogen --help
uv run visiogen render-graph --graph tests/fixtures/graphs/headphone.json --output artifacts/release/headphone.vsdx --debug-dir artifacts/release/headphone-debug
uv run visiogen validate artifacts/release/headphone.vsdx --json-report artifacts/release/headphone-validation.json
```

Also confirm:
- no secrets or GGUF files are tracked;
- the canonical template checksum is unchanged by test/generation runs;
- normal tests make no network calls;
- integration tests are opt-in;
- output determinism holds for saved-graph rendering except package metadata explicitly normalized/ignored;
- Windows acceptance report identifies the exact commit and artifact checksums.

**Suggested commits:**
- `Add end-to-end acceptance artifacts`
- `Document Visiogen setup and limitations`
- `Complete baseline acceptance`

**Definition of done:** A user can explicitly select local Qwen or Gemini, describe a supported diagram, inspect each JSON boundary, receive a structurally valid editable `.vsdx`, and open/move/relabel/reconnect/save the file in Microsoft Visio without a repair prompt. Representative 5–25 element outputs are useful first drafts, and known limitations are explicit.

---

## 13. Agent Handoff Checklist Per Milestone

Every implementation handoff must include:

1. **Scope completed:** exact task IDs and files changed.
2. **RED evidence:** test name and expected pre-implementation failure.
3. **GREEN evidence:** focused and relevant suite command/output.
4. **Artifacts:** exact paths and checksums where binary outputs matter.
5. **Commit:** plain commit message and commit hash after user-approved Git setup.
6. **Risks/open defects:** classified by pipeline stage, never hidden.
7. **Next gate:** prerequisites still outstanding, especially Windows validation.

Do not report a milestone complete when only structural ZIP/XML checks pass if its gate requires Microsoft Visio. Do not continue past a failed critical gate by weakening acceptance criteria.

## 14. Primary Risks and Required Responses

| Risk | Required response |
|---|---|
| `vsdx` API cannot create genuinely glued connectors | Stop at M2; test alternate proven template/package strategy before M6. |
| Template binary merge conflict | Single template editor; separate binary commits; maintain inventory docs. |
| Local Qwen slow/inaccurate | Benchmark same fixtures; tune context/quantization; retain explicit Gemini option. |
| LLM invents semantics | Narrow DTO, extra-field rejection, one repair retry, reviewed golden graphs. |
| Container/coordinate bugs | Pure layout contract, one y-axis conversion, geometry invariants. |
| Dense/crossing-heavy diagrams | Grow page, wrap labels, document 5–25 element target; no perfect-routing detour. |
| Structural validator passes broken Visio file | Keep Windows exact-commit acceptance as a distinct release gate. |
| Scope drifts toward CAD/design patents | Reject/defer physical geometry and filing-readiness claims. |

## 15. Deferred Work

Only after M9 passes: multi-page `PatentDocument`, figure-wide reference numbering, advanced callout/orthogonal routing, themes, arbitrary stencil packs, image/sketch input, SVG/CAD renderers, and provider auto-selection with explicit user consent.
