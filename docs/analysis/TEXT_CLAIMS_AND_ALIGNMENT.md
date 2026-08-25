# Text Claims and Entity Alignment

**Status:** Phase A5 in progress; deterministic selection and core workflows implemented

A5 independently converts bounded document prose into evidence-bound atomic claims,
then aligns claim entities with A3 diagram objects. Claim extraction does not receive
the A3 diagram interpretation on its first pass.

## Implemented passage selection

`select_relevant_text` selects exact `TextBlock` records using:

- candidate asset anchors and linked captions;
- bounded neighboring-block proximity;
- figure-number cross-references;
- exact visible-label and reference-number matches;
- explicit user-selected block IDs;
- page-region proximity when page coordinates are available.

Selection is ordered, block- and character-bounded, never truncates a source block,
and explicitly records relevant blocks omitted by limits.

## Implemented claim contract

The structured workflow records exact source spans with block IDs and zero-based
offsets, atomic predicates, exact and conservatively normalized subjects/objects,
modality, scope, qualifiers, exhaustive wording, current-figure relevance, confidence,
and ambiguity. Hard validation rejects spans outside selected blocks, mismatched text,
unknown evidence, invalid normalization, and incompatible negation/exhaustive scope.

The selected prose is delimited as untrusted data. One bounded repair may correct only
schema, IDs, spans, normalization, modality, or scope; it may not introduce new claims.

## Implemented entity alignment

Alignment currently applies these layers in order:

1. exact reference numeral;
2. exact normalized visible label;
3. explicit alias claims that refer to the current figure;
4. length-sensitive conservative fuzzy matching with a uniqueness margin;
5. unresolved output with alternatives rather than a forced match.

Short labels of three characters or fewer never receive fuzzy matching. Every result
retains its claim/evidence references, method, score, and alternatives.

## Remaining A5 work

- expand controlled modality, negation, exhaustive-scope, alias, and short-label fixtures;
- add optional evidence-bound model-assisted alignment after deterministic layers;
- run the clean production claim extractor over the reviewed corpus;
- preserve exact prompts/responses and score span, modality, scope, and alignment quality;
- close A5 only after ambiguous entities remain unresolved and all evidence gates pass.
