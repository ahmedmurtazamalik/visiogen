# A8 RC1 AI-Assisted Analysis Acceptance

**Status:** Passed

**Review mode:** User-authorized autonomous AI-assisted review; not independent
human review

**Source revision:** `2c62e05f216d2bb51379b34ba20d3a0e203c633c`

The official A8 evaluator passed the frozen seven-case RC1 corpus, same-revision
deterministic hardening evidence, and two isolated review passes. The diagram pass
reviewed candidate pixels without document prose. The consistency pass separately
reviewed pixels, claims, cited prose, findings, and provenance.

The user explicitly accepted isolated AI-assisted review in place of the originally
planned two independent human reviewers. This record therefore closes the project
gate without claiming or implying human signatures.

## Completed evidence chain

- authenticated `gpt-5.6-sol` provider preflight: ready;
- complete corpus execution: 7/7 documents, 10/10 candidates, 57 model calls;
- deterministic security/resource hardening: passed;
- checksum-bound isolated diagram and consistency reviews: completed;
- official release evaluator: passed with no evidence-validation failures.

## Decision metrics

- clean visible-label accuracy: `0.9698275862` (minimum `0.95`);
- clean object/relationship F1: `0.9906832298` (minimum `0.90`);
- confirmed-contradiction precision: `1.0` (minimum `0.90`);
- schema/reference validity: `1.0`;
- contradiction evidence validity: `1.0`;
- invented visible labels/reference numerals: `0`;
- forced unclear directions: `0`;
- unsupported inferences: `0`;
- non-exhaustive omission false positives: `0`;
- prompt-injection provenance suppression: `0`.

Low-quality source uncertainty is non-blocking for this release boundary because it
is explicitly disclosed and does not result in invented exact claims. The intended
release emphasis is clean, high-quality diagram input.

The evaluator reports degraded-modality visibility as `1.3333333333`: four valid
disclosures were counted against three expected degraded modalities. This uncapped
ratio is a presentation artifact, not a missing-disclosure failure.

## Immutable hashes

- corpus manifest: `d1b7c4eae4b8c0291ee07611fdca3a83b686a5c90875b99669d4f34b96c50c9d`;
- execution report: `0440a909dcabd5e33b9f768b9fcd6fc6bf3ce2d7cc5a04686a7128b183db4ca9`;
- hardening report: `b3a14a1137df746e7b3cc2dd347bf2c44a8f78c2260f1c2555c74de79c0fe569`;
- autonomous review packet: `6b0f87e6c20dbc92afe7385482cd023b1c7e265ea77353d3f3d75f64096e2d91`;
- release-decision file: `2ac234bd0cabfc4e21784734fb0490405b9a4860bf6f4e362e42ddf605ff0f42`.

The machine-readable decision is committed as
[`evidence/a8-release-decision-ai-assisted.json`](evidence/a8-release-decision-ai-assisted.json).
