# A4 Faithful Description Acceptance

**Date:** 2026-08-25

**Decision:** Passed; Phase A4 complete

## Accepted source and input

- Source revision: `07352f4b1148ccf2a7ef0724e2f81416ba2252ca`
- Source state: clean
- Generator: `deterministic-a4-description-v1`
- Accepted A3 source revision: `95722f2a846472deef0da818d236ca2f7b45df38`
- A3 report SHA-256: `6c909130ea1667d9dcb7cbd12dee03c22ca6a1f4f1222a7800c7a3c1e4d851c5`
- A4 acceptance-report SHA-256: `eb67f1f3133c7a695a1f7ae93cdd8ee1a1783ecdc1318c7cac4f266366e81622`

The checksum-bound [exact acceptance report](evidence/a4-faithful-description.json)
records the input provenance, source revision, thresholds, per-case coverage, output
stability, and SHA-256 hashes for every generated Markdown and JSON artifact.

## Coverage results

The runner composed descriptions for all six exact semantic models accepted by A3.

| Measure | Required | Result |
|---|---:|---:|
| Object coverage | 1.00 | 1.00 |
| Relationship coverage | 1.00 | 1.00 |
| Group coverage | 1.00 | 1.00 |
| Legend coverage | 1.00 | 1.00 |
| Limitation coverage | 1.00 | 1.00 |
| Visible-label coverage | 1.00 | 1.00 |
| Reference-number coverage | 1.00 | 1.00 |
| Ambiguity coverage | 1.00 | 1.00 |
| Byte-stable repeated output | required | yes |

## Deterministic guarantees

Automated tests separately prove:

- canonical eight-section order, including explicit empty sections;
- exact visible title, object, group, relationship-label, and reference rendering;
- relationship direction, endpoint uncertainty, containment, and grouping narration;
- explicit alternatives, disconnected elements, and source limitations;
- rejection of unknown or omitted semantic references;
- source-controlled Markdown escaping;
- JSON round-trip stability without mutating the input model;
- atomic publication and byte-identical repeated artifacts.

## Scope of the decision

This closes deterministic textual description for validated A3 diagrams. It does not
claim that A3 has perfect coverage on arbitrary real documents; that remains an A8
held-out evaluation concern. It also does not select nearby document prose, extract
claims, align entities, or report inconsistencies. Those capabilities begin in A5.
