# G3 — AI Construction Planner

**Status:** Complete

G3 defines and validates the complete AI-authored visual construction plan before
deterministic compilation. The implementation is split across commits `f5aaff6`,
`6f4496b`, and `501a32a`; real-model feedback produced the focused callout
diagnostic correction in `0df508d`.

The first clean-checkpoint run retained a failure showing that an object without a
reference numeral received a semantic-note callout. The validator rejected it,
but its finding was insufficiently actionable. The corrected prompt explicitly
permits reference callouts only for non-null reference numerals, and the validator
now tells the model to omit an invalid callout.

The corrected clean-source run at `0df508d` passed with real `gpt-5.6-sol` plans
for all core families:

- flowchart: passed on the first attempt;
- system block: passed on the first attempt; and
- component schematic: passed after one bounded repair.

The external 22-file evidence bundle retains exact specifications, logical and
transport prompts, raw responses, validated plans, timings, schema/prompt/example
versions, model identity, source revision, and per-artifact hashes. Its sorted
relative-path/file-hash inventory SHA-256 is
`354b4c92fafcef5251643bcd8d26784a808ec648355c55f24fdcd1eb5561a37c`.
The checked-in machine-readable summary is
[`evidence/g3-construction-planner.json`](evidence/g3-construction-planner.json).

This gate proves planner schema completeness and real-model plan validity. It does
not claim compilation, rendering, visual quality, or native Microsoft Visio
acceptance; those remain G4–G10 work.
