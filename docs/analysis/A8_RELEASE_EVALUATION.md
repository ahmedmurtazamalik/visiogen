# A8 Release Evaluation Contract

**Status:** Implemented; real held-out execution and human review pending

Phase A8 evaluates only the PDF/DOCX diagram-analysis path. It does not include
VSDX generation or Microsoft Visio acceptance.

## Corpus discipline

Every source document is identified by SHA-256 and assigned before model execution
to either `development` or `held_out`. Prompt or policy tuning may use development
cases. The release decision is calculated exclusively from held-out cases. A corpus
must include clean PDF and DOCX inputs, degraded inputs, multiple diagram/non-diagram
content, a vector PDF, reference numerals, and an adversarial prompt-injection case.
The scorer resolves only normalized relative paths beneath the corpus directory,
rejects symlinks and hash mismatches, and prevents identical source bytes from
appearing in both splits. Held-out coverage is machine-checked for all seven case
families listed in the A8 plan.

DOCX cases must explicitly declare one inspection mode. The first release accepts
`portable` extraction: native OOXML text, tables, captions, relationships, and
embedded raster media. `rendered_word` and `rendered_libreoffice` remain unsupported
until separate platform-specific corpora pass. Portable reports must disclose that
Word shapes, SmartArt, charts, and text boxes were not rendered.

## Blinded review

Each held-out case has one checksum-bound review record with two passes:

1. Diagram review compares the source pixels with the structured diagram and
   description while document prose is hidden.
2. Consistency review compares findings against both pixels and cited prose.

The release evaluator rejects missing, duplicate, or unblinded held-out reviews.
Development reviews never contribute to release metrics.

## Release gates

The evaluator implements the frozen A0 thresholds: complete schema/reference and
dual-evidence validity; at least 95% clean visible-label accuracy; at least 90%
clean object/relationship F1; at least 90% confirmed-contradiction precision; full
visibility of degraded modalities; and zero invented labels/reference numerals,
forced unclear directions, non-exhaustive omission false positives, or adversarial
provenance suppression.

Run the scorer after corpus execution and review:

```bash
uv run python scripts/evaluate_analysis_release.py \
  --corpus /immutable/a8-corpus.json \
  --reviews /immutable/a8-reviews.json \
  --output /immutable/a8-release-decision.json
```

The output binds the decision to the exact corpus and review files. A passing score
is necessary but not sufficient for release: security/resource-limit tests, source
immutability, exact provider/model identity, complete evidence bundles, and known
limitations must also be included in the final acceptance record.
