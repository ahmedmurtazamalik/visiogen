# Visual Observation and Semantic Reconstruction

**Status:** Phase A3 complete; clean real-provider quality gate passed

A3 converts the model-ready images produced by A2 into two separate validated
records. The observation stage records literal pixels without document prose. The
reconstruction stage interprets only those observations and the same images.

## Implemented contracts

The observation contract records:

- exact visible text with alternatives and confidence;
- objects, containers, connectors, arrowheads, legends, notes, callouts, and groups;
- explicit properties rather than unconstrained JSON dictionaries;
- evidence regions bound to one overview or tile derivative;
- bounding boxes and connector paths local to that named derivative;
- legibility and coverage warnings.

Application code validates derivative and evidence references and transforms every
tile-local box and point into normalized source-image coordinates. The model is not
trusted to perform coordinate transforms.

The semantic contract records:

- family, orientation, visible title, confidence, and limitations;
- objects with exact and normalized labels, types, shapes, references, containment,
  alternatives, and visual evidence;
- relationships with nullable endpoints, endpoint certainty, direction, kind, line
  style, path, label, alternatives, and evidence;
- visually supported groups and legend mappings.

## Hard validation

Code rejects:

- duplicate or unresolved evidence, observation, object, relationship, or group IDs;
- evidence attached to a different derivative than observation geometry;
- invalid tile-to-source coordinate transforms;
- invented visible labels, titles, relationship labels, and reference numerals;
- invalid normalized labels;
- unknown parents, endpoints, group members, or evidence references;
- object containment cycles;
- object geometry that does not intersect cited visual evidence;
- known connector endpoints whose paths do not begin/end near the cited objects;
- high-confidence relationships whose direction is explicitly unclear.

Each stage receives at most one structural repair. Repair prompts prohibit adding
new visual claims. Overview and tiles are checksum-verified before every call, and
the composed workflow enforces the A0 limit of four model calls per candidate.

## Current interface

```python
from visiogen.analysis import (
    SemanticAnalysisWorkflow,
    StructuredObservationWorkflow,
    StructuredReconstructionWorkflow,
)

workflow = SemanticAnalysisWorkflow(
    StructuredObservationWorkflow(observation_caller),
    StructuredReconstructionWorkflow(reconstruction_caller),
)
result = workflow.analyze(prepared_candidate, candidate_bundle)
```

The observation and reconstruction callers use different strict output schemas even
when backed by the same provider/model.

## Acceptance

The reviewed six-case corpus covers branching, containment, connector crossings,
reference numerals, dense tiling, and an ambiguous damaged arrowhead. On 2026-08-25,
the clean production-adapter run passed every threshold with 1.00 object precision,
object recall, edge precision, edge recall, direction accuracy, family accuracy, and
reference recall. The ambiguous control was retained as uncertain rather than forced
into a direction.

The exact prompts, raw responses, image hashes, validated outputs, scores, and provider
identity are preserved in
[`../acceptance/A3_VISUAL_SEMANTICS.md`](../acceptance/A3_VISUAL_SEMANTICS.md).
Broader held-out real-document quality remains an A8 concern; Phase A4 can now consume
the validated semantic model to produce faithful textual descriptions.
