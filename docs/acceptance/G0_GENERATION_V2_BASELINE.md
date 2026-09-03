# G0 — Generation v2 Baseline and Contract Freeze

**Status:** Complete

**Baseline source revision:** `2c56b13`

G0 establishes the immutable inputs and quality rules for Generation v2. It does
not claim that Generation v1 passes the new visual rubric.

## Completed work

- Frozen ten-case corpus covering every family required by the Generation v2 plan.
- Machine-readable semantic expectations, required visual conditions, and
  forbidden defects for every case.
- Frozen quality thresholds for semantic fidelity, overlaps, connector/label
  collisions, callouts, direction, containment, human preference, and repeated-run
  completion.
- Strict corpus and baseline schemas with coverage, cross-reference, evidence, and
  status validation.
- Reproducible baseline-report builder.
- Human review rubric and review-record format.
- Honest Generation v1 baseline report covering every frozen case.

## Frozen artifacts

```text
tests/fixtures/generation_v2/corpus.json
sha256: c7ecae968ee8c763d78a1d4cb8bd99c21a6b548fabc804ad93ecf078bd71d236

docs/acceptance/evidence/g0-generation-v1-baseline.json
sha256: c0ce2f4fa1ce0c0e1e159d567b08e71cc9adfc63aa1937d21e63ee79e135f21e
```

The baseline report embeds the corpus checksum. The baseline builder reproduces
the same semantic report when invoked with the same inputs.

## Verification

Existing generation-owned suite before adding the six G0 contract tests:

```text
257 passed in 37.48s
```

G0 contract tests:

```text
6 passed in 0.09s
```

Combined generation-owned gate:

```text
263 passed in 38.74s
```

Full repository integration gate:

```text
537 passed in 46.64s
```

## Baseline result

The Generation v1 baseline is **incomplete**, not failed and not passed. This G0
environment is Linux and cannot create authoritative Microsoft Visio previews or
native lifecycle evidence. All ten cases are present in the report and explicitly
marked `unavailable` with the reason.

Existing historical artifacts do not fill that gap:

- M6 R2 previews were rejected and superseded after visible routing defects.
- The later three-case hybrid bundle records `visual_critique_performed: false`
  and retains no final preview.
- No current checksum-bound Windows corpus report exists for the frozen ten cases.

G9 must run comparable Generation v1 cases when feasible and retain unavailable
comparisons explicitly. It may not discard unavailable cases or treat them as
passing evidence.

## G0 decision

The corpus, evaluation rules, schemas, report format, and local baseline state meet
the G0 exit contract. The granular checkpoint lineage is:

```text
51ad0e2  Freeze Generation v2 evaluation corpus
f9b9abc  Record Generation v1 baseline availability
9ba57e2  Document Generation v2 quality baseline
```

The active plan contains the complete phase record. Generation v1 visual evidence
remains incomplete by design and cannot be upgraded without a new checksum-bound
Windows run.
