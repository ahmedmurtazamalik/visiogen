# A3 Visual Semantics Acceptance

**Date:** 2026-08-25

**Decision:** Passed; Phase A3 complete

## Accepted source and provider

- Source revision: `95722f2a846472deef0da818d236ca2f7b45df38`
- Source state: clean
- Provider: Codex CLI 0.146.0
- Model: `gpt-5.6-sol`
- Corpus version: 1
- Corpus SHA-256: `d2b6ef9e2eb9a0d237d687df1a69f6135dfcb0f6bdae1bee9602fabf87a7db6a`
- Acceptance-report SHA-256: `6c909130ea1667d9dcb7cbd12dee03c22ca6a1f4f1222a7800c7a3c1e4d851c5`

The checksum-bound [exact acceptance report](evidence/a3-semantic-reconstruction.json)
retains both model stages, logical and transport prompts, raw structured responses,
validated observations and semantic models, image hashes, timing, provider identity,
per-case scores, thresholds, and aggregate metrics.

## Semantic reconstruction results

The immutable locally generated corpus covers branching flow, object containment,
visible reference numerals, crossing connectors without a junction, a dense diagram
requiring six overlapping tiles, and a deliberately damaged arrowhead.

| Measure | Required | Result |
|---|---:|---:|
| Object precision | 0.90 | 1.00 |
| Object recall | 0.90 | 1.00 |
| Reference recall | 1.00 | 1.00 |
| Edge precision | 0.85 | 1.00 |
| Edge recall | 0.85 | 1.00 |
| Direction accuracy | 0.90 | 1.00 |
| Diagram-family accuracy | 0.80 | 1.00 |
| Ambiguous directions handled safely | all | 1/1 |

All six cases completed in one clean-source production-adapter run. Every case used
one observation call and one reconstruction call, below the four-call per-candidate
limit. No case invented a visible object label or reference numeral. The ambiguity
control retained `unclear` direction, competing interpretations, reduced confidence,
and an explicit limitation instead of fabricating certainty.

## Deterministic guarantees

Automated tests separately prove:

- derivative checksums are verified before every model call;
- overview and tile coordinates are transformed into source-image coordinates;
- evidence, object, relationship, group, endpoint, and containment references resolve;
- visible labels, normalized labels, titles, and reference numerals remain evidence-bound;
- known connector paths begin and end near their claimed objects;
- unclear direction cannot carry high confidence;
- each stage permits at most one evidence-preserving repair;
- failed reconstruction evidence retains both attempts and exact validation findings.

## Scope of the decision

This closes visual observation and semantic reconstruction for the controlled MVP
corpus. It does not claim accuracy on arbitrary real-world documents; broader held-out
evaluation remains Phase A8. It also does not yet produce the final human-readable
diagram description or compare diagrams with document prose. Those capabilities begin
in Phases A4 and A5.
