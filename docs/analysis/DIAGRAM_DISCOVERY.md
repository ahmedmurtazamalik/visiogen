# Diagram Discovery and Image Preparation

**Status:** Phase A2 complete

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
- checksum-bound PNG derivatives and atomic `candidates.json` publication;
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

## Acceptance

The clean-source `gpt-5.6-sol` acceptance run achieved 1.00 diagram precision and
recall, 1.00 non-diagram precision and recall, and correctly preserved the ambiguous
control as `unknown`. Perceptual embedded/page matching passed a positive containment
fixture and an unrelated-chart false-match control. Exact prompts, responses, hashes,
metrics, and provider identity are preserved in
[`../acceptance/A2_DIAGRAM_DISCOVERY.md`](../acceptance/A2_DIAGRAM_DISCOVERY.md).

## Deliberate limitations

- The accepted corpus is deliberately small and synthetic; broader held-out document
  testing remains a Phase A8 release gate.
- Caption and alt-text cues can select obvious diagram assets, but image-only
  candidates require the multimodal classifier.
- Public `visiogen analyze` discovery flags arrive with the composed analysis CLI;
  the current interface is library-only.
- Preparation crops full images unless a validated classifier returns a tighter
  normalized region.
