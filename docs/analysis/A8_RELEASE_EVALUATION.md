# A8 Release Evaluation Contract

**Status:** Passed for 0.1.0 RC1 under autonomous AI-assisted review

The frozen seven-case execution, same-revision hardening gate, and official scorer
passed at revision `2c62e05`. The user explicitly authorized two isolated AI review
passes in place of the originally planned independent human reviewers. This is an
accepted project-policy deviation and is not represented as human review. See
[`../acceptance/A8_AI_ASSISTED_ACCEPTANCE.md`](../acceptance/A8_AI_ASSISTED_ACCEPTANCE.md).

Phase A8 evaluates only the PDF/DOCX diagram-analysis path. It does not include
VSDX generation or Microsoft Visio acceptance.

The candidate release boundary and limitations are frozen in
[`A8_SUPPORTED_SCOPE.md`](A8_SUPPORTED_SCOPE.md). The held-out decision approves an
exact provider/model and evidence set within that boundary; it does not establish
reliable understanding of arbitrary documents.

## Corpus discipline

Every source document is identified by SHA-256 and assigned before model execution
to either `development` or `held_out`. Prompt or policy tuning may use development
cases. The release decision is calculated exclusively from held-out cases. A corpus
must include clean PDF and DOCX inputs, degraded inputs, multiple diagram/non-diagram
content, a vector PDF, reference numerals, and an adversarial prompt-injection case.
The scorer resolves only normalized relative paths beneath the corpus directory,
rejects symlinks and hash mismatches, and prevents identical source bytes from
appearing in both splits. Held-out coverage is machine-checked for all seven case
families listed in the A8 plan.

Copy
[`A8_CORPUS_DRAFT.example.json`](A8_CORPUS_DRAFT.example.json), place reviewed
documents beneath its `sources/` directory, and freeze the exact bytes before any
provider call:

```bash
uv run python scripts/freeze_analysis_release_corpus.py \
  --draft /review/a8-corpus-draft.json \
  --output /review/a8-corpus.json
```

The freezer adds source hashes, applies all corpus admission rules, and refuses to
overwrite an existing frozen manifest. The example names required roles only; it
does not provide or imply accepted real documents.

The maintained corpus sourcing strategy uses four provenance buckets: U.S.
government technical reports, published patent records, redistributable open
research/open-source material, and locally authored controlled/adversarial
documents. Controlled documents exercise containers and security behavior but do
not count as independent evidence of arbitrary-document quality. The local control
builder is `scripts/build_analysis_release_controls.py`; every concrete corpus must
record upstream URLs, hashes, transformations, and licensing/reuse status beside the
frozen manifest.

DOCX cases must explicitly declare one inspection mode. The first release accepts
`portable` extraction: native OOXML text, tables, captions, relationships, and
embedded raster media. `rendered_word` and `rendered_libreoffice` remain unsupported
until separate platform-specific corpora pass. Portable reports must disclose that
Word shapes, SmartArt, charts, and text boxes were not rendered.

## Blinded review contract

Each held-out case has one checksum-bound review record with two passes:

1. Diagram review compares the source pixels with the structured diagram and
   description while document prose is hidden.
2. Consistency review compares findings against both pixels and cited prose.

The release evaluator rejects missing, duplicate, or unblinded held-out reviews.
Development reviews never contribute to release metrics.

For RC1, the two passes were completed in isolated AI-assisted contexts with
distinct reviewer identifiers. Future checkpoints may return to human reviewers or
retain this policy, but must state the selected review mode in their acceptance
record.

Generate review forms only after the complete corpus execution passes:

```bash
uv run python scripts/prepare_analysis_release_reviews.py \
  --corpus /immutable/a8-corpus.json \
  --execution /immutable/a8-execution/execution-report.json \
  --output /immutable/a8-reviews.json
```

The generated packet contains only held-out cases, preserves exact execution-bundle
hashes, starts every human judgment as `null`, and refuses to overwrite an existing
review file. Reviewers replace all nulls without editing case IDs or bundle hashes.

## Corpus execution

First run the provider preflight. It requires one quick structured text response
followed by two consecutive complete executions of the clean native-PDF case. It
reports `READY` only when the text call takes at most 30 seconds and no production
model call takes more than 240 seconds:

```bash
uv run python scripts/run_analysis_provider_preflight.py \
  --corpus /immutable/a8-corpus.json \
  --output /immutable/a8-provider-preflight \
  --model gpt-5.6-sol \
  --timeout 300
```

Do not start the full corpus unless `preflight-report.json` has `status: "ready"`.
A non-ready result is operational evidence, not an analysis-quality failure.

Run the admitted corpus from a clean source checkout and publish evidence outside
the repository:

```bash
uv run python scripts/run_analysis_release_corpus.py \
  --corpus /immutable/a8-corpus.json \
  --output /immutable/a8-execution \
  --model gpt-5.6-sol
```

The runner uses the production pipeline, isolates every case, preserves raised and
partial failures, verifies manifest artifact hashes, rejects dirty-source provenance
and VSDX artifacts, and hashes each complete bundle for subsequent human review.
Selecting individual `--case` values produces exploratory evidence and can never
pass the complete-corpus gate.

## Deterministic hardening gate

Security and resource-limit evidence is published separately from model-quality
evidence so a provider rerun cannot obscure a deterministic regression:

```bash
uv run python scripts/run_analysis_hardening_acceptance.py \
  --output /immutable/a8-hardening
```

The curated gate covers obfuscated PDF active content, encrypted and external PDF
content, unsafe DOCX ZIP/XML constructs, macro/ActiveX and expansion limits, input
and decoded-pixel ceilings, tile budgets, prompt-injection quoting, source-controlled
Markdown escaping, atomic artifact publication, partial-result preservation, failed
call provenance, and analysis-only bundle enforcement. The report binds the exact
test files and source revision and retains JUnit plus captured process output.

## Release gates

The evaluator implements the frozen A0 thresholds: complete schema/reference and
dual-evidence validity; at least 95% clean visible-label accuracy; at least 90%
clean object/relationship F1; at least 90% confirmed-contradiction precision; full
visibility of degraded modalities; and zero invented labels/reference numerals,
forced unclear directions, non-exhaustive omission false positives, or adversarial
provenance suppression.

Run the scorer after corpus execution and review:

```bash
uv run python scripts/evaluate_analysis_release.py \
  --corpus /immutable/a8-corpus.json \
  --reviews /immutable/a8-reviews.json \
  --execution /immutable/a8-execution/execution-report.json \
  --hardening /immutable/a8-hardening/acceptance-report.json \
  --output /immutable/a8-release-decision.json
```

The output binds the decision to the exact corpus, review, execution, and hardening
files. Reviews must cite the exact executed bundle hash, the diagram and consistency
passes must have distinct reviewer identities, every corpus case must have completed,
and execution plus deterministic hardening must come from the same clean source
revision. A passing score
is necessary but not sufficient for release: security/resource-limit tests, source
immutability, exact provider/model identity, complete evidence bundles, and known
limitations must also be included in the final acceptance record.
