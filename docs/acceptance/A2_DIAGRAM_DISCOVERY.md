# A2 Diagram Discovery Acceptance

**Date:** 2026-08-25

**Decision:** Passed; Phase A2 complete

## Accepted source and provider

- Source revision: `a1245451e47633a1ee6ef6ee9c0dc785ba90aaf6`
- Source state: clean
- Provider: Codex CLI 0.146.0
- Model: `gpt-5.6-sol`
- Corpus version: 1
- Corpus SHA-256: `9c3d55703452c0291047ce4bb2a30eb025db5b1ff558c5887446405c39fb7cc3`
- Acceptance-report SHA-256: `40e2107cd5c01d08aae5b6a29907f6a8ec376729bf675352a16d428fa3005258`

The checksum-bound [exact acceptance report](evidence/a2-candidate-classification.json)
retains the logical and transport prompts, raw structured response, per-image hashes,
model and provider identity, elapsed time, strict decisions, discovery result, thresholds,
and metrics.

## Classification results

The immutable locally generated corpus contains three supported diagrams, four explicit
non-diagrams, and one intentionally illegible ambiguous control.

| Measure | Required | Result |
|---|---:|---:|
| Diagram precision | 0.90 | 1.00 |
| Diagram recall | 0.90 | 1.00 |
| Non-diagram precision | 0.90 | 1.00 |
| Non-diagram recall | 0.90 | 1.00 |
| Ambiguous controls classified `unknown` | all | 1/1 |

Every case received a strict label, confidence, and reason. The model did not promote
the blurred control into a confident diagram or non-diagram decision.

## Deterministic preparation and deduplication

Automated tests separately prove:

- exact SHA-256 grouping while preserving identical renders on different pages;
- conservative embedded-image/page-render matching and recovered page region;
- rejection of an unrelated chart false-match control;
- a hard limit on perceptual comparisons;
- source-asset checksum verification before decoding;
- bounded crop, overview, and overlapping-tile generation;
- atomic failure when a candidate exceeds its tile limit;
- stable derivative bytes, hashes, normalized regions, and `candidates.json` output;
- explicit selected, ignored, unknown, filtered, and limit-skipped dispositions.

## Scope of the decision

This closes candidate discovery and image preparation for the controlled MVP corpus.
It does not claim accuracy on arbitrary document imagery. Broader held-out real-document
evaluation remains part of Phase A8. It also does not claim visual object, label, or
connector reconstruction; those capabilities begin in Phase A3.
