# Hybrid-AI Migration Verification Record

**Date:** 2026-08-20
**Provider/model:** Codex CLI 0.146.0 / `gpt-5.6-sol`
**Status:** DESIGN/RENDER PIPELINE IMPLEMENTED; MICROSOFT VISIO PREVIEW, CRITIQUE, AND NATIVE ACCEPTANCE REMAIN OPEN

## Corrected preview boundary

Microsoft Visio is the only supported VSDX preview/export authority. The production preview adapter uses desktop Visio COM automation on Windows to open the generated document read-only and export page one as PNG. It fails explicitly when Windows or Visio is unavailable; it does not substitute another VSDX renderer.

Earlier local image-critique bundles were generated through an out-of-scope preview mechanism introduced during development. Those bundles have been withdrawn and deleted. They are not product evidence, are not archived for acceptance, and do not support any visual-quality claim.

Because this Linux host does not provide desktop Microsoft Visio, the corrected full loop cannot be accepted locally. The valid local scope is:

1. authentic structured model design;
2. hard schema, reference, finite-geometry, placement, overlap, page-bound, containment, and connector-hint validation;
3. native editable VSDX rendering;
4. bounded ZIP/XML package validation; and
5. exact prompt, raw-response, design, layout, source, template, and output provenance.

The following remain unverified until the exact candidate runs on Windows with desktop Visio:

- Visio-exported preview generation;
- image-based critique of that Visio preview;
- one bounded revision and Visio rerender preview;
- open without repair;
- native editability and connector attachment after movement; and
- save, close, and reopen stability.

## Security and provenance hardening

The production adapter:

- uses an ephemeral read-only Codex workspace;
- ignores Codex user configuration and executable rules;
- gives model-run shell commands no inherited environment;
- passes the Codex process only a small runtime/auth environment allowlist;
- preserves exact post-adapter transport prompts and raw responses;
- records source revision and worktree cleanliness;
- hashes the request, template, schemas, output, preview, and evidence artifacts;
- rejects non-empty or symlinked evidence directories and reserved output collisions, including `manifest.json.tmp`;
- rejects a renderer returning an unexpected output path;
- writes evidence privately; and
- bounds ZIP member count, expanded size, individual size, and compression ratio before XML parsing.

The Codex CLI remains an agentic local trust boundary with read access under its sandbox policy. This MVP accepts trusted local diagram requests. Adversarial third-party documents require stronger OS/container isolation or a non-agentic provider adapter.

## Template masters

Direct package analysis established why generated files contain roughly 20 master XML files. `templates/template.vsdx` carries 19 master definitions plus the `masters.xml` catalog, and the renderer retains that complete catalog. The representative basic-system output references only four masters—Dynamic connector, Database, Rounded Rectangle, and Circle—leaving 15 unused.

This is package bloat, not 19 page dependencies. Pruning is deferred until the implementation atomically updates the catalog, relationships, content types, master parts, and per-master relationships, then passes desktop Microsoft Visio open/edit/save/reopen acceptance.

## Automated verification

Current corrected-tree results:

- Full automated suite: **248 tests passed**.
- Focused Ruff checks passed for the migration modules and tests.
- Focused mypy checks passed for the seven hybrid source modules.
- Source distribution and wheel built successfully.
- `git diff --check` passed.
- A real Codex CLI `--no-critique` run completed through the public command, produced a structurally valid VSDX whose recomputed SHA-256 matched its manifest, recorded `visual_critique_performed: false`, and produced no preview files. The temporary dirty-worktree bundle was deleted and is not acceptance evidence.

Repository-wide Ruff/mypy have pre-existing issues outside the focused migration gate and must not be represented as passing.

## Remaining acceptance sequence

The Windows runner and native lifecycle harness are implemented in
`scripts/run_windows_hybrid_corpus.ps1` and `scripts/validate_in_visio.ps1`.
Their execution contract is documented in
[`WINDOWS_VISIO.md`](WINDOWS_VISIO.md).

1. Pull the exact candidate into a clean Windows checkout with desktop Microsoft Visio installed.
2. Run the three-case stochastic corpus through `scripts/run_windows_hybrid_corpus.ps1` without disabling critique.
3. Preserve each Visio-exported preview and real-provider critique.
4. Apply at most one validated revision per case.
5. Let the native harness open and move named endpoint shapes in each checksum-matched final file.
6. Save, close, reopen, and verify shape/connection stability through Visio COM.
7. Perform the documented human visual review of hierarchy, labels, crossings, callouts, and visible glue.
8. Archive exact source revision, template hash, prompts, responses, previews, original/resaved VSDX hashes, and Visio acceptance reports.

Until those steps pass, the architecture and local design/render implementation are available, but product-level visual/native acceptance is not complete.
