# Text Claims and Entity Alignment

**Status:** Phase A5 complete; clean real-provider quality gate passed

A5 independently converts bounded document prose into evidence-bound atomic claims,
then aligns claim entities with A3 diagram objects. Claim extraction does not receive
the A3 diagram interpretation on its first pass.

## Implemented passage selection

`select_relevant_text` selects exact `TextBlock` records using:

- candidate asset anchors and linked captions;
- bounded neighboring-block proximity;
- figure-number cross-references;
- token-bounded diagram-title, object-label, connector-label, and reference-number
  matches;
- explicit user-selected block IDs;
- page-region proximity when page coordinates are available.

Selection is ordered, block- and character-bounded, never truncates a source block,
and explicitly records relevant blocks omitted by limits.

## Implemented claim contract

The structured workflow records exact source spans with block IDs and zero-based
offsets, atomic predicates, exact and conservatively normalized subjects/objects,
modality, scope, qualifiers, exhaustive wording, current-figure relevance, confidence,
and ambiguity. Hard validation rejects spans outside selected blocks, mismatched text,
unknown evidence, entities absent from their cited spans, invalid normalization, and
incompatible negation/exhaustive scope. Both failed attempts retain their exact traces
and final validation error.

The selected prose is delimited as untrusted data. One bounded repair may correct only
schema, IDs, spans, normalization, modality, or scope; it may not introduce new claims.

## Implemented entity alignment

Alignment currently applies these layers in order:

1. exact reference numeral;
2. exact normalized visible label;
3. unambiguous medium/high-confidence asserted or required alias claims that refer to
   the current figure;
4. length-sensitive conservative fuzzy matching with a uniqueness margin;
5. unresolved output with alternatives rather than a forced match.

Short labels of three characters or fewer never receive fuzzy matching. Every result
retains its claim/evidence references, method, score, and alternatives.

## Acceptance

The clean production-adapter run passed all seven reviewed cases with 1.00 claim recall,
modality accuracy, exact-span validity, alias alignment, ambiguity safety, and exhaustive
scope recognition. Exact evidence is recorded in
[`../acceptance/A5_TEXT_CLAIMS.md`](../acceptance/A5_TEXT_CLAIMS.md). Optional semantic
alignment remains a future extension rather than an MVP requirement because the accepted
deterministic layers resolve supported cases and preserve ambiguous alternatives.
