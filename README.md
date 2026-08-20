# Visiogen

Visiogen converts natural-language requests into editable native Microsoft Visio `.vsdx` diagrams. It targets flowcharts, system diagrams, and abstract component or patent-oriented schematics.

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

The detailed contract is [`docs/HYBRID_AI_ARCHITECTURE.md`](docs/HYBRID_AI_ARCHITECTURE.md). The bounded migration plan is [`hybrid_ai_implementation_plan.md`](hybrid_ai_implementation_plan.md). The older implementation plans are retained as historical milestone records.

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

## Development

```bash
uv run pytest -q
uv run visiogen --help
uv build
```

Fake provider runners are used only for low-level schema, process, retry, and orchestration tests. They are not AI-quality evidence. Real-provider acceptance artifacts must come through the production adapter and retain their prompts and responses.

## Existing milestone evidence

- [`docs/M4_EXTRACTION.md`](docs/M4_EXTRACTION.md) records actual Codex, Gemini, and local-Qwen extraction runs as well as unit/contract evidence.
- [`docs/M5_LAYOUT.md`](docs/M5_LAYOUT.md) records the former deterministic Graphviz/fallback baseline, which is now a fallback rather than the product-wide visual authority.
- [`docs/M6_RENDERING.md`](docs/M6_RENDERING.md) records native template rendering and the current Microsoft Visio acceptance status.

Linux ZIP/XML validation is structural evidence only. Microsoft Visio is the sole preview/export and native-behavior authority for visual critique, repair prompts, editability, connector movement, and save/close/reopen behavior.

## Windows hybrid acceptance

The final three-case corpus and native Visio lifecycle gate are automated by:

```powershell
.\scripts\run_windows_hybrid_corpus.ps1 `
  -OutputDirectory "C:\VisiogenAcceptance\hybrid-$(git rev-parse --short HEAD)" `
  -Model "gpt-5.6-sol" `
  -Visible
```

The output path must not already exist and must be outside the source checkout. The runner requires clean immutable source, performs real Visio-exported visual critique, then opens, moves, saves, closes, and reopens each final VSDX through desktop Microsoft Visio. Its report remains pending until the documented human visual review is completed. See [`docs/WINDOWS_HYBRID_ACCEPTANCE.md`](docs/WINDOWS_HYBRID_ACCEPTANCE.md) for prerequisites, exact evidence, manual visual checks, and failure handling.

## Template masters

The renderer currently retains the canonical template's complete master catalog. The template contains 19 master definitions plus `masters.xml`; a representative basic-system drawing references only Dynamic connector, Database, Rounded Rectangle, and Circle. The other 15 definitions are package bloat, not page dependencies. Pruning is deferred until coordinated catalog, relationship, content-type, and part cleanup has dedicated tests and the pruned result passes Microsoft Visio open/edit/save/reopen acceptance.
