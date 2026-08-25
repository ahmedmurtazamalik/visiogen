# A6 Consistency Engine Acceptance

**Date:** 2026-08-25

**Decision:** Passed; Phase A6 complete

## Accepted source and corpus

- Base source revision: `7eba14d5e2386d172ed9e2b097e5610bf79bbfc8`
- Source state: content-addressed A6 implementation and corpus
- Implementation SHA-256: `9cab627a49e0f0d30b6b370bbcd1b33edd62e8d06546608046d6a91093c54a61`
- Provider: none; deterministic production comparison engine
- Model calls: 0
- Corpus version: 1
- Corpus SHA-256: `253291da573f56339d0957875afeb41ba61c032034221fceff5076442ebabfed`
- Acceptance-report SHA-256: `2fe9def77371731d2dbe557d8561e9cfc0a56b992e47381aece2c2d1d1227bc3`

The checksum-bound [exact acceptance report](evidence/a6-consistency.json) retains
every semantic diagram, document claim, entity alignment, production finding,
expected outcome, per-case score, threshold, and implementation/corpus checksum.

## Controlled matrix results

The 39-case corpus supplies contradiction, consistent, and ambiguous variants for
each of the 13 planned categories: label, reference number, object existence,
relationship, direction, relationship type, containment, sequence, modality,
negation, alias, exhaustive scope, and unreadable evidence.

| Measure | Required | Result |
|---|---:|---:|
| Case agreement | 1.00 | 1.00 |
| Confirmed-contradiction precision | ≥0.90 | 1.00 |
| Evidence validity | 1.00 | 1.00 |
| Ambiguous cases handled safely | 1.00 | 1.00 |
| Non-exhaustive omission false positives | 0 | 0 |

All 39 cases completed through `compare_diagram_and_claims`. Every decisive
cross-source finding cites diagram and text evidence. Missing relationships are
reported as probable rather than confirmed contradictions, unreadable evidence
downgrades confidence, unresolved entities remain unverifiable, and non-exhaustive
prose never creates an omission finding.

## Model-assisted boundary

Automated tests separately prove that bounded semantic adjudication receives exactly
one proposition pair and only its cited evidence, allows one schema-only repair,
preserves the original evidence and propositions, and cannot emit a confirmed
contradiction or decide which source is authoritative. Real-provider quality for
semantic equivalence remains part of the broader held-out A8 evaluation rather than
the deterministic A6 gate.

## Scope of the decision

This closes the A6 comparison rules, finding contracts and validators, evidence and
confidence policy, omission safeguards, bounded adjudication boundary, human-readable
finding sections, controlled matrix, and gate scoring. Phase A7 still needs to wire
these components into the public multi-candidate analysis pipeline, CLI, and complete
provenance bundle.
