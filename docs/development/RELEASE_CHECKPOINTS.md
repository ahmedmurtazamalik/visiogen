# Release Checkpoints and Repeatable A8 Reruns

This procedure preserves a stable point from which Visiogen quality can be improved
and the complete release evaluation can be repeated without overwriting historical
evidence.

## Checkpoint contract

1. Commit all intended source, tests, and documentation.
2. Require a clean checkout synchronized with its intended remote branch.
3. Create an annotated release-candidate tag such as `v0.1.0-rc1`.
4. Never change that checkout during preflight, corpus execution, hardening, or
   review preparation.
5. Put evidence outside the source checkout in a new directory containing the short
   revision. Never reuse or overwrite an earlier evidence directory.
6. Record the exact tag, full revision, corpus hash, provider, model, and report
   hashes in the release record.

Later improvements branch from the accepted checkpoint or current `main`, receive a
new commit and release-candidate tag, and run the entire sequence again. Targeted
case runs are exploratory only and can never replace a complete corpus execution.

## Verification before a checkpoint

```bash
UV_CACHE_DIR=/tmp/visiogen-uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/visiogen-uv-cache uv build
UV_CACHE_DIR=/tmp/visiogen-uv-cache uv run visiogen --help
git diff --check
git status --short --branch
```

## Complete analysis release cycle

Set a shell variable that does not overlap with system configuration:

```bash
VISIOGEN_REVISION=$(git rev-parse --short HEAD)
VISIOGEN_ACCEPTANCE_ROOT=/absolute/path/to/visiogen-acceptance
VISIOGEN_CORPUS=/absolute/path/to/a8-corpus/corpus.json
```

Run the authenticated readiness gate first:

```bash
UV_CACHE_DIR=/tmp/visiogen-progress-uv-cache uv run python \
  scripts/run_analysis_provider_preflight.py \
  --corpus "$VISIOGEN_CORPUS" \
  --output "$VISIOGEN_ACCEPTANCE_ROOT/a8-preflight-$VISIOGEN_REVISION" \
  --model gpt-5.6-sol \
  --timeout 300
```

Continue only when `preflight-report.json` reports `ready`:

```bash
UV_CACHE_DIR=/tmp/visiogen-progress-uv-cache uv run python \
  scripts/run_analysis_release_corpus.py \
  --corpus "$VISIOGEN_CORPUS" \
  --output "$VISIOGEN_ACCEPTANCE_ROOT/a8-full-$VISIOGEN_REVISION" \
  --model gpt-5.6-sol \
  --timeout 300
```

Continue only when the complete corpus reports `passed`:

```bash
UV_CACHE_DIR=/tmp/visiogen-progress-uv-cache uv run python \
  scripts/run_analysis_hardening_acceptance.py \
  --output "$VISIOGEN_ACCEPTANCE_ROOT/a8-hardening-$VISIOGEN_REVISION"

UV_CACHE_DIR=/tmp/visiogen-progress-uv-cache uv run python \
  scripts/prepare_analysis_release_reviews.py \
  --corpus "$VISIOGEN_CORPUS" \
  --execution "$VISIOGEN_ACCEPTANCE_ROOT/a8-full-$VISIOGEN_REVISION/execution-report.json" \
  --output "$VISIOGEN_ACCEPTANCE_ROOT/a8-reviews-$VISIOGEN_REVISION.json"
```

Two independent humans then complete the distinct diagram and consistency passes.
Reviewer identities and judgments must never be generated or inferred. Afterward:

```bash
UV_CACHE_DIR=/tmp/visiogen-progress-uv-cache uv run python \
  scripts/evaluate_analysis_release.py \
  --corpus "$VISIOGEN_CORPUS" \
  --reviews "$VISIOGEN_ACCEPTANCE_ROOT/a8-reviews-$VISIOGEN_REVISION.json" \
  --execution "$VISIOGEN_ACCEPTANCE_ROOT/a8-full-$VISIOGEN_REVISION/execution-report.json" \
  --hardening "$VISIOGEN_ACCEPTANCE_ROOT/a8-hardening-$VISIOGEN_REVISION/acceptance-report.json" \
  --output "$VISIOGEN_ACCEPTANCE_ROOT/a8-decision-$VISIOGEN_REVISION.json"
```

## Generation acceptance

The same tagged revision must separately run the three-case Windows corpus in
desktop Microsoft Visio and receive its manual visual review. Follow
[`../acceptance/WINDOWS_VISIO.md`](../acceptance/WINDOWS_VISIO.md). Linux package
validation and screenshots never substitute for this gate.

## Release and improvement tags

- `v0.1.0-rcN`: immutable candidate used for acceptance evidence.
- `v0.1.0-experimental`: initial user-facing experimental checkpoint after the
  documented release decision.
- `v0.1.x-rcN`: later reliability improvements followed by a complete new corpus,
  hardening, human review, and Windows lineage when generation code changes.

Tags are local until explicitly pushed. Publishing a tag or package is a separate
release action and should occur only after its recorded gates and limitations match
the intended release claim.
