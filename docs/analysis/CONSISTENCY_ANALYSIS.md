# Consistency Analysis

Phase A6 compares the validated diagram reconstruction from A3 with the independently
extracted and aligned document claims from A5. The comparison layer does not reopen
the source document, reinterpret pixels, or assume that either source is correct.

## Execution policy

Deterministic rules run first. They cover exact identity and label evidence,
reference mappings, existence and negation, relationships, direction, relationship
type, containment, sequence, cardinality, exhaustive scope, and supported
diagram-internal warnings. Possible and example modalities do not impose mandatory
diagram facts. Missing relationships remain probable rather than confirmed because a
faint or unrecognized connector could explain the absence.

Semantic adjudication is limited to one unresolved proposition pair and only its
cited evidence. It can confirm semantic consistency, retain a terminology
difference, suggest a probable contradiction, or require review. It cannot produce a
confirmed contradiction, inspect unrelated content, or choose an authoritative
source.

## Finding contract

Every finding retains:

- normalized diagram and text propositions;
- diagram and text evidence IDs from each applicable side;
- category, status, severity, and calibrated confidence;
- an explanation, explicit uncertainty where required, and a human review action.

Confirmed contradictions require medium or high confidence and evidence from both
sources. Low-confidence disagreements are downgraded to probable contradictions.
Unresolved alignment is never treated as proof that an object is absent.

## Omission policy

An unmentioned diagram component is not an omission. `possible_omission` is available
only when evidence-bearing claims explicitly mark an inventory as exhaustive. Strict
coverage does not manufacture a text citation when no exhaustive claim exists.

## Acceptance

The controlled corpus contains contradiction, consistent, and ambiguous variants for
all 13 planned comparison categories. Run it with:

```bash
uv run python scripts/run_analysis_consistency_corpus.py \
  --output artifacts/a6-consistency.json
```

The accepted result and thresholds are documented in
[`../acceptance/A6_CONSISTENCY.md`](../acceptance/A6_CONSISTENCY.md).
