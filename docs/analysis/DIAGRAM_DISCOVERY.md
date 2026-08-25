# Diagram Discovery and Image Preparation

**Status:** Phase A2 in progress; deterministic foundation implemented

A2 operates only on an admitted `DocumentSnapshot` and its checksum-bound visual
assets. It does not reconstruct diagram semantics or compare diagrams with prose.

## Implemented boundary

The current slice provides:

- stable candidate enumeration from every `VisualAsset`;
- exact SHA-256 duplicate grouping, preferring an embedded original over an
  identical page render;
- deterministic rejection of assets too small to contain useful diagram evidence;
- conservative caption/alt-text cues without treating surrounding prose as visual
  truth;
- a strict diagram, non-diagram, or unknown classification contract;
- a provider-neutral structured multimodal classifier workflow;
- explicit page/candidate filters and configured candidate limits;
- a disposition and reason for every enumerated candidate;
- bounded image decoding with source checksum verification;
- normalized region cropping, overview resizing, overlapping tiles, and tile limits;
- checksum-bound PNG derivatives and atomic `candidates.json` publication.
- a balanced, locally generated candidate corpus with reviewed diagram,
  non-diagram, and ambiguous labels.

Unknown candidates remain visible and are not selected automatically. An explicit
candidate selection may admit an unknown candidate for human-directed analysis.
Known non-diagram assets cannot be selected.

## Library interfaces

```python
from visiogen.analysis import (
    CandidateSelection,
    discover_diagram_candidates,
    prepare_diagram_candidates,
)

discovery = discover_diagram_candidates(
    snapshot,
    classifier=classifier,
    selection=CandidateSelection(page_number=2),
)

prepared = prepare_diagram_candidates(
    snapshot,
    discovery,
    "artifacts/document-ingestion",
    "artifacts/diagram-candidates",
)
```

The classifier is injected through a narrow protocol. The included structured
workflow accepts real image files and strict schema-constrained provider output,
but no provider is silently selected by the library.

## Deliberate limitations

- Deduplication currently proves exact byte identity. Perceptual matching between
  an embedded original and a page render still needs reviewed image-matching tests.
- Caption and alt-text cues can select obvious diagram assets, but image-only
  candidates require the multimodal classifier.
- The real-provider precision/recall report is not yet complete, so the A2
  acceptance gate remains open.
- Public `visiogen analyze` discovery flags arrive with the composed analysis CLI;
  the current interface is library-only.
- Preparation crops full images unless a validated classifier returns a tighter
  normalized region.

## Remaining A2 acceptance work

1. execute the production multimodal adapter against the immutable corpus;
2. record candidate precision, recall, unknown rate, and crop adequacy;
3. add perceptual embedded-image/page-render grouping with false-match controls;
4. freeze the classifier prompt/model identity and preserve exact run evidence;
5. close A2 only after every fixture receives a reviewed disposition and reason.
