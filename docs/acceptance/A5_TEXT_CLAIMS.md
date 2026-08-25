# A5 Text Claims and Alignment Acceptance

**Date:** 2026-08-25

**Decision:** Passed; Phase A5 complete

## Accepted source and provider

- Source revision: `2150781c3c7941415f23b4b1939337e665785a70`
- Source state: clean
- Provider: Codex CLI 0.146.0
- Model: `gpt-5.6-sol`
- Corpus version: 1
- Corpus SHA-256: `adac521b6da4980a7156e52275ba6c3c1096c020a8c66b4f4149e3edd015a37c`
- Acceptance-report SHA-256: `a83b2a782b0a635eabaca4cdefca26eefb85ee83047d8d38e0d90d34f7655d80`

The checksum-bound [exact acceptance report](evidence/a5-text-claims.json) retains
logical and transport prompts, raw responses, exact selected prose and span offsets,
validated claims, alignment results, timing, provider identity, and scores.

## Results

The seven-case corpus covers requirements, negation, possibility, example scope,
explicit aliases, duplicate short labels, reference numerals, and exhaustive inventory
wording.

| Measure | Required | Result |
|---|---:|---:|
| Claim recall | 0.90 | 1.00 |
| Modality accuracy | 1.00 | 1.00 |
| Exact-span validity | 1.00 | 1.00 |
| Explicit-alias alignment | 1.00 | 1.00 |
| Ambiguous entity unresolved | 1.00 | 1.00 |
| Exhaustive-scope recognition | 1.00 | 1.00 |

All seven cases completed on their first provider attempt. Every selected entity with a
unique reference numeral aligned exactly; the duplicated one-character label remained
unresolved with alternatives rather than being forced to either object.

## Scope

This closes bounded passage selection, independent atomic claim extraction, and
conservative entity alignment for the controlled MVP corpus. Broader real-document
evaluation remains A8. Claim/diagram comparison and inconsistency findings begin in A6.
