# A7 Vertical Analysis Pipeline Acceptance

**Date:** 2026-08-25

**Decision:** Passed; Phase A7 complete

## Accepted source and provider

- Source revision: `3641464d380a02f86e4654317173fa541f25ae15`
- Source state: clean and content-addressed
- Implementation SHA-256: `320793b715a7d267de8e7d2e7ff247b85a77c059d877495431d7decb4ce1056f`
- Provider: Codex CLI 0.146.0
- Model: `gpt-5.6-sol`
- Acceptance-report SHA-256: `b373de88c738cc045263bbcc2440cf56775823c56e165568e2f0379b0d4ab518`

The checksum-bound [acceptance report](evidence/a7-vertical-pipeline.json) records
the exact revision, provider, model, fresh input hashes, complete bundle hashes,
source/tool/schema provenance, timings, call counts, artifact inventories, warnings,
and failure lists for both cases.

## Vertical results

| Case | Candidates | Calls | Bundle artifacts | Result |
|---|---:|---:|---:|---|
| Fresh native-text PDF with rendered page diagram | 1 | 5 | 41 | Passed |
| Fresh native-text DOCX with embedded diagram image | 1 | 4 | 39 | Passed |

Both documents were generated immediately before the run. Their source hashes were
bound into their manifests, and every manifest-listed artifact was independently
rehashed before the runner returned success. Each case retained classification,
observation, reconstruction, and claim-extraction prompts and raw responses; the
validated semantic model, accessible description, selected prose, claims,
alignments, comparison input, findings, aggregate JSON, and Markdown report; and
source, tool, schema, timing, and partial-failure provenance.

For both source formats, the model reconstructed the three visible labeled objects
`Sensor`, `Processor`, and `Actuator`, plus the two forward relationships labeled
`measurements` and `commands`. Related native prose produced structured claims. The
DOCX result confirmed both visible sequences; both formats conservatively marked a
caption/title assertion unverifiable because no title was visible inside the
prepared diagram image.

The public report byte-matched the report in each private bundle. No `.vsdx` file
appeared anywhere in either bundle, and the analysis pipeline did not invoke the
generation, layout, rendering, preview, or Microsoft Visio paths.

## Portable DOCX limitation retained

The accepted DOCX case uses native paragraphs and an embedded raster image. Its
manifest intentionally retains the portable-mode warning that Word drawing layout,
shapes, SmartArt, charts, and text boxes are not rendered. This is not hidden or
treated as complete DOCX visual coverage. Platform-specific Word rendering and
broader held-out documents remain A8 concerns.

## Scope of the decision

A7 closes production orchestration, public CLI execution, atomic report/evidence
publication, multi-candidate and partial-result behavior, bounded semantic
adjudication integration, and hash-bound provenance for the controlled fresh PDF and
DOCX vertical slice. It does not claim general accuracy on arbitrary diagrams or
full fidelity for native Word drawing objects. Those quality and scope decisions
remain Phase A8.
