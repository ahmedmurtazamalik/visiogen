# Generation v2 Analysis Import

**Status:** G2 implemented contract

The G2 bridge converts one completed diagram from a Visiogen analysis evidence
bundle into a reviewable `DiagramSpecification`. The bridge belongs to generation
and deliberately duplicates its narrow input DTOs; it does not import analysis or
document-ingestion modules.

## Workflow

Produce a draft specification without generating a diagram:

```bash
uv run visiogen generate \
  --analysis-bundle artifacts/review/evidence \
  --stop-after-specification \
  --output artifacts/reconstruction/draft-spec.json
```

If the bundle contains more than one completed diagram, select one explicitly:

```bash
uv run visiogen generate \
  --analysis-bundle artifacts/review/evidence \
  --analysis-candidate candidate-0002 \
  --stop-after-specification \
  --output artifacts/reconstruction/draft-spec.json
```

A reviewer can edit the JSON and generate from the corrected artifact with
`--spec-file`. Omitting `--stop-after-specification` projects and immediately
passes the validated draft into the normal generation pipeline.

## Trust and validation boundary

The bridge requires a non-symlink bundle directory and a strict current
`manifest.json`. It selects only manifest-listed
`candidate-NNNN/24-analyzed-diagram.json` files. It verifies the byte length and
SHA-256 checksum of both the analyzed diagram and its corresponding
`14-validated-observations.json` before parsing either artifact.

Every title, object, relationship, group, legend, and annotation evidence ID must
resolve in that validated observation set. Multiple completed candidates require
explicit selection. Unsafe paths, duplicate artifact paths, candidate/path
mismatches, checksum changes, dangling evidence, and invalid source records fail
before projection.

## Projection rules

Supported high-confidence objects and relationships retain their visible labels,
reference numerals, containment, directions, grouping, and evidence IDs. The
specification source records the PDF/DOCX identity and checksum, analysis provider
and model, selected candidate, manifest checksum, and analyzed-diagram checksum.

Unsupported semantic types receive a provisional generic component type and a
review item. Relationships with ambiguous endpoints, unclear direction, unknown
kind, non-high confidence, or alternatives are not asserted; they become explicit
review items with their evidence references. Object alternatives, uncertain
groups, annotations, legends, limitations, unknown family, and unsupported
orientation are likewise retained for review rather than silently resolved.

Fixture bundles are synthetic deterministic contract fixtures. They establish
projection and provenance behavior, not analysis-model or generation quality.
