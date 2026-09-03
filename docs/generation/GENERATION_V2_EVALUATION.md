# Generation v2 Quality Evaluation Contract

**Status:** G0 frozen evaluation contract

**Corpus:** `tests/fixtures/generation_v2/corpus.json`

This document defines how Visiogen Generation v1 and v2 outputs are evaluated.
It separates semantic correctness, measurable visual defects, professional visual
judgment, native Microsoft Visio behavior, and execution reliability. Passing one
category cannot compensate for failing another hard gate.

## 1. Evidence requirements

Every evaluated case must be bound to:

- corpus and case identifier;
- source revision and clean-worktree state;
- provider, exact model, prompt version, and schema version;
- input specification hash;
- initial and final construction-plan hashes where applicable;
- initial and final VSDX hashes;
- Microsoft Visio-exported preview hashes;
- diagnostic measurement hashes;
- visual critique and patch history;
- native Visio acceptance report; and
- human review record.

An unavailable artifact is recorded as unavailable. It is never assigned a passing
score. Third-party renderers and Linux package inspection cannot substitute for a
Microsoft Visio preview or native lifecycle test.

## 2. Evaluation dimensions

### 2.1 Semantic fidelity — hard gate

Review the final diagram against the case's expected objects, relationships,
directions, labels, containment, reference numerals, and required conditions.

Record:

- expected and correctly rendered objects;
- invented objects;
- expected and correctly rendered relationships;
- invented relationships;
- correct relationship directions;
- correct required containment;
- preserved exact labels where required;
- preserved uncertainty for analysis-import cases; and
- each unmet required or violated forbidden condition.

Every required relationship direction and containment assertion must be correct.
An invented material object or relationship fails the case even if the composition
is attractive.

### 2.2 Deterministic visual defects — hard gate

Count defects against the final construction geometry and diagnostic overlay:

- shape/shape, shape/label, and label/label overlaps;
- arrowheads inside unrelated shapes;
- connectors crossing unrelated labels;
- callout leaders crossing unrelated labels;
- objects outside page or container bounds;
- connector endpoints not on their declared source/target;
- truncated or out-of-bounds text regions; and
- violations of case-specific minimum clearance.

The frozen initial thresholds allow zero overlap, arrowhead, connector/label, or
callout/label defects.

### 2.3 Professional visual review — hard gate

Review the final Visio-exported preview at normal viewing scale. Score each item
from 1 (unacceptable) to 5 (professional first draft):

| Dimension | Review question |
|---|---|
| Readability | Are labels, directions, and references immediately readable? |
| Hierarchy | Does visual emphasis match semantic importance? |
| Flow | Is the primary reading order obvious without tracing every line? |
| Routing | Are routes economical, distinguishable, and free of confusing bends? |
| Spacing | Is density deliberate, with sufficient whitespace and clearance? |
| Grouping | Are containment and peer relationships visually unambiguous? |
| Balance | Does the page feel composed rather than merely populated? |
| Notation | Are shapes, colors, arrows, and line styles semantically consistent? |
| Editability | Does the visual design remain usable as a professional first draft? |

Any score of 1 or any unresolved high-severity defect fails the case. For the V1
versus V2 comparison, reviewers also record `prefer_v1`, `prefer_v2`, or `tie`
without seeing engine identity where blinding is practical. V2 must be preferred in
at least 80% of non-tied comparisons.

### 2.4 Native Visio behavior — hard gate

On desktop Microsoft Visio:

1. open without repair, recovery, conversion, or unreadable-content warnings;
2. select and edit every expected shape, label, connector, and callout;
3. move both endpoints of representative and high-risk connectors;
4. verify endpoints remain attached to sensible declared ports or boundaries;
5. move every callout target and verify its leader remains attached;
6. save under a new name, close Visio, and reopen;
7. repeat movement checks; and
8. verify connection signatures, shape counts, and coordinates survive reopening.

One native failure fails the case. Structural ZIP/XML validity is necessary but not
sufficient.

### 2.5 Reliability and efficiency — release gate

For selected cases, execute multiple fresh production-model runs. Record:

- total attempts and completed runs;
- invalid initial plans and successful repairs;
- visual-edit iteration count;
- repeated-state or budget stops;
- model and end-to-end latency;
- input/output token use where available; and
- provider or Visio failures separately from quality failures.

At least 90% of supported-scope runs must complete with an approved final preview
and passing native artifact. The report must show both first-attempt validity and
eventual completion so repair does not hide planner instability.

## 3. Frozen thresholds

The authoritative machine-readable thresholds live in the corpus:

| Metric | Threshold |
|---|---:|
| Shape or label overlaps | 0 |
| Arrowheads inside unrelated shapes | 0 |
| Connectors crossing unrelated labels | 0 |
| Callout leaders crossing unrelated labels | 0 |
| Required relationship direction accuracy | 100% |
| Required containment accuracy | 100% |
| Unresolved high-severity findings | 0 |
| Blind-review preference for V2 | at least 80% |
| Supported-run completion | at least 90% |

Threshold changes require a new corpus version and written rationale committed
before evaluating the implementation against them. Historical reports retain the
old corpus hash and thresholds.

## 4. Review record

Each human review should record:

```text
case_id:
reviewer_id:
reviewed_vsdx_sha256:
reviewed_preview_sha256:
engine_identity_hidden: true/false

semantic_fidelity:
  objects_correct/expected:
  relationships_correct/expected:
  direction_correct/expected:
  containment_correct/expected:
  invented_objects:
  invented_relationships:
  required_condition_failures:
  forbidden_condition_violations:

professional_scores_1_to_5:
  readability:
  hierarchy:
  flow:
  routing:
  spacing:
  grouping:
  balance:
  notation:
  editability:

high_severity_findings:
preference: prefer_v1/prefer_v2/tie/not_applicable
notes:
```

Reviewer identity and judgments must be supplied by the actual reviewer. They may
not be generated or inferred by the pipeline.

## 5. G0 baseline interpretation

The checked-in G0 baseline report records contract-test health and the availability
of comparable Generation v1 evidence. The frozen ten-case corpus has not been run
through the current pipeline on Windows. Those cases are therefore marked
`unavailable`, and the baseline is `incomplete`.

The older M6 R2 previews are useful historical defect evidence but were explicitly
rejected and superseded. The later three-case hybrid bundle used real model design
but skipped visual critique and retained no final previews. Neither set is a valid
complete V1 comparison baseline for the frozen corpus.

G0 can close with that evidence unavailable because the state is explicit and
checksum-bound. G9 must compare V2 against any V1 cases that can be produced from
the frozen corpus and must report unavailable V1 comparisons rather than silently
dropping them.
