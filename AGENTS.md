# Visiogen Engineering Contract

Visiogen is an experimental Python 3.11+ toolkit with two independent product
paths:

- **Generation:** turn a natural-language request into an editable Microsoft
  Visio `.vsdx` first draft.
- **Analysis:** inspect diagrams in PDF or DOCX documents, reconstruct their
  visible meaning, and compare that meaning with related document text.

Optimize for a reliable product, short feedback loops, auditable AI behavior, and
code a small team can understand. Do not optimize for hypothetical scale or add
enterprise infrastructure without a current, measured need.

These instructions apply to planning, implementation, review, refactoring, and
testing throughout this repository. More specific instructions in a nested
`AGENTS.md` override this file for that subtree.

## Sources of truth

Read only the documentation relevant to the task. Use these current documents as
authoritative:

- `README.md` for supported product behavior and development commands.
- `docs/architecture/HYBRID_AI.md` for the generation pipeline and the boundary
  between model judgment and deterministic enforcement.
- `docs/plans/active/DOCUMENT_ANALYSIS.md` and `docs/analysis/` for the analysis
  contracts and supported scope.
- `docs/development/WORKSTREAMS.md` for ownership boundaries, dependency
  direction, and shared integration files.
- `docs/development/RELEASE_CHECKPOINTS.md` for release-quality analysis reruns.
- `docs/acceptance/WINDOWS_VISIO.md` for native Visio acceptance.

Documents under `docs/plans/archive/` and `docs/acceptance/archive/` are historical
evidence, not current architecture. Do not revive superseded designs unless the
user explicitly asks.

## Governing rule

Implement the smallest clear change that satisfies the user's stated outcome and
preserves Visiogen's supported boundary. Every added file, dependency,
abstraction, configuration option, validation branch, model call, artifact, and
test must be justified by a current requirement or a reproduced failure.

Before changing code, state concisely:

1. The concrete outcome.
2. Assumptions that materially affect the implementation.
3. The smallest viable approach.
4. What will deliberately not be built.
5. The narrowest useful verification.

Ask only when ambiguity would materially change the result. Otherwise choose the
simplest reversible interpretation and proceed.

## Product and architecture boundaries

Keep generation and analysis independent.

- Generation code lives in the established top-level `src/visiogen/` modules and
  `src/visiogen/generation/`. It must not import analysis or document-ingestion
  code.
- Deterministic document ingestion lives in `src/visiogen/documents/`. It must not
  import providers, analysis workflows, or generation/VSDX modules.
- Analysis code lives in `src/visiogen/analysis/`. It may depend on `documents`
  and narrow shared provider/configuration infrastructure, but not on the VSDX
  renderer, layouts, templates, preview exporter, or native Visio automation.
- Treat `src/visiogen/cli.py`, `src/visiogen/config.py`,
  `src/visiogen/providers/`, `src/visiogen/__init__.py`, `pyproject.toml`,
  `README.md`, `.github/workflows/`, and `tests/conftest.py` as shared integration
  surfaces. Keep changes to them small and task-specific.
- Do not extract shared infrastructure merely because both product paths contain
  similar code. Share only a proven identical contract after both implementations
  have stabilized.

The root CLI is a dispatcher. Put generation command behavior in
`src/visiogen/generation/command.py` and analysis command behavior in
`src/visiogen/analysis/command.py`.

## AI and deterministic responsibilities

Maintain the hybrid design deliberately.

- Models may perform semantic interpretation, composition, proposed geometry,
  visual observation, claim extraction, and critique.
- Python remains authoritative for schemas, references, containment, geometry
  invariants, document safety limits, evidence binding, artifact publication, and
  VSDX package correctness.
- Never ask a model to author VSDX XML or ShapeSheet formulas directly.
- Preserve explicit uncertainty. Do not turn ambiguous visual evidence into a
  confident relationship, claim, or inconsistency.
- Keep analysis claims traceable to diagram regions or document text. Do not
  silently discard provenance needed by downstream findings.
- Preserve the existing bounded repair/revision behavior. Do not add open-ended
  model retries or agent loops.
- Treat prompts, validated model responses, previews, manifests, checksums, and
  timing/provider identity as product evidence where the current workflow records
  them.

Fake providers are suitable for deterministic schema, process, retry, and
orchestration tests. They are not evidence of model quality. Do not present mocked
or synthetic output as real-provider acceptance.

## VSDX and document safety

- Preserve editability and native Visio behavior; a structurally valid ZIP/XML
  package alone is not proof that a generated diagram works correctly.
- Microsoft Visio on Windows is authoritative for preview/export, connector
  behavior, editability, and open/save/close/reopen acceptance.
- Linux generation with `--no-critique` is a supported partial workflow, not visual
  acceptance.
- Keep deterministic validation between model output and rendering.
- Treat diagram requests as trusted local input under the current generation
  threat model. Do not claim isolation for adversarial third-party prompts that
  the production adapter does not provide.
- Preserve archive, decompression, media, relationship, and path-safety checks for
  untrusted PDF/DOCX input. Security limits protecting document ingestion are
  product behavior, not optional hardening.
- Do not expand the documented PDF/DOCX or diagram-type support boundary without
  implementation, tests, and corresponding documentation.

## Simplicity rules

- Prefer a direct function over a new class, framework, service, registry,
  factory, strategy, or plugin system.
- Do not abstract single-use code. Extract only when real duplication makes the
  result easier to understand.
- Use the standard library or existing dependencies when adequate.
- Do not add caches, queues, background workers, unbounded retries, concurrency,
  distributed coordination, or observability systems without measured need.
- Do not add configuration switches unless both behaviors are required now.
- Match the local style. Do not reformat, rename, type, document, or refactor
  adjacent code unless the requested outcome requires it.
- Prefer deleting or consolidating obsolete code over hiding it behind another
  interface.
- Every changed line must trace to the requested outcome.

## Testing and acceptance

Tests protect supported behavior and evidence contracts; they do not exist to
maximize count or coverage.

- For a bug, reproduce it with the smallest practical test before fixing it.
- Add tests for user-visible behavior, schema or evidence contracts, meaningful
  boundaries, package safety, or realistic failures with material impact.
- Do not test library/runtime behavior, trivial accessors, cosmetic formatting,
  private implementation details, or impossible combinations.
- Prefer one representative behavior test over a matrix of near-duplicates.
- Do not rewrite frozen fixtures or recorded provider evidence merely to make a
  change pass. If a contract intentionally changes, create clearly identified new
  evidence and explain the lineage.
- Tests marked `integration` may require a real provider or desktop application;
  do not assume they are available in the local environment.
- Run the narrowest relevant test while iterating. Use these standard gates from
  the repository root:

```bash
# Generation work
uv run pytest -q tests --ignore=tests/analysis --ignore=tests/documents

# Analysis and document-ingestion work
uv run pytest -q tests/analysis tests/documents

# Shared or release-level integration
uv run pytest -q
uv build
uv run visiogen --help
```

Real-provider acceptance and Windows Visio acceptance are separate from the unit
suite. Run them only when the task requires them and the necessary environment and
authorization are available. Retain the exact provenance artifacts they produce.

Never let verification loop indefinitely. After two substantially identical
failures, diagnose the cause and change approach. If the remaining blocker is the
environment, an external provider, or unavailable Microsoft Visio, report it
plainly. Default to a 10-minute verification budget unless the user authorizes a
longer run.

## Refactoring and scope

When asked to simplify or improve performance:

1. Identify the actual maintenance or runtime cost.
2. Establish the cheapest reliable baseline.
3. Make one coherent change at a time.
4. Preserve supported behavior and evidence contracts.
5. Delete code and tests made genuinely redundant.
6. Re-measure and keep only changes with a demonstrated benefit.

Do not perform a wholesale rewrite, framework migration, schema redesign,
provider replacement, or VSDX template overhaul merely because it might be
cleaner. Propose such work separately with evidence.

Keep unrelated findings in a short parking-lot note; do not fix them. Stop when
the requested behavior works and the smallest relevant verification passes.

## Completion report

Report only:

- What changed and why.
- What became simpler or faster, with evidence when applicable.
- Verification performed and its duration.
- Any concrete remaining risk or environmental blocker.

Before finishing, confirm that the change respects workstream import boundaries,
preserves provenance and deterministic safety checks, uses tests tied to realistic
behavior, and adds no unnecessary layer, dependency, option, model call, or
artifact.
