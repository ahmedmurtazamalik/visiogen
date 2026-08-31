# A8 Provisional AI-Assisted Review and Remediation

**Date:** 2026-08-31

**Status:** Provisional review failed; general evidence-policy remediation implemented;
fresh execution pending

This record is not independent human acceptance. Two isolated `gpt-5.6-sol`
review passes graded the immutable seven-case execution from revision `f962073`:
one image-only diagram pass and one case-scoped consistency pass. The complete
packet, audit trail, and decision are preserved outside the source checkout under
`acceptance/` with the suffix `ai-provisional-f962073`.

## Provisional decision

Passing metrics included schema/reference validity, clean visible-label accuracy,
clean object/relationship F1, expected degradation disclosure, non-exhaustive
omission safety, and prompt-injection provenance retention.

The provisional decision failed because it identified:

- 46 connector semantic-type assertions without visible labels or legend support;
- one connector direction asserted without cited arrowhead evidence;
- six exact labels asserted from degraded, non-high-confidence text observations;
- one false confirmed contradiction that compared the spatial value `left` with a
  connector direction.

## General remediation

The implementation now applies source-independent precision rules after semantic
reconstruction:

1. an unlabeled connector has relationship type `unknown` unless a visible,
   validated legend explicitly supports the type;
2. a directional connector without cited arrowhead evidence has direction
   `unclear` and cannot retain high confidence;
3. when observation warnings identify degraded or poor-quality source text, an
   exact object label requires a matching high-confidence visible-text observation;
   otherwise the label and reference numerals are omitted with an explicit
   limitation;
4. document claims using spatial values such as `left` are not compared with the
   connector-direction enum and remain unverifiable.

These policies are covered by development regression tests rather than assertions
against held-out A8 bundle contents. After implementation, all 217 analysis tests
and the complete 519-test suite passed.

## Next gate

Commit the remediation, keep the `f962073` evidence immutable, and run a fresh
seven-case corpus plus deterministic hardening from the new clean revision. Any
subsequent AI-assisted review remains provisional until replaced by the two distinct
human review passes required by the frozen A8 release contract.
