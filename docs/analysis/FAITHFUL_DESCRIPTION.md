# Faithful Textual Description

**Status:** Phase A4 complete; deterministic acceptance gate passed

A4 turns one validated A3 `AnalyzedDiagram` into readable Markdown and strict JSON.
It does not rescan the image and does not make another model call. This keeps the
human-readable description mechanically aligned with the accepted semantic model.

## Output contract

Every description contains the same eight sections:

1. diagram identity;
2. layout and reading order;
3. containers and groups;
4. object inventory;
5. relationships;
6. legends, notes, and callouts;
7. ambiguities and disconnected elements;
8. visibility and interpretation limitations.

Each sentence is a `DescriptionStatement` with explicit object, relationship, group,
legend, limitation, and evidence references. The validator rejects unknown references,
missing high-impact elements, omitted visible labels or reference numerals, hidden
unclear directions, and incomplete legend or limitation coverage.

Markdown rendering escapes source-controlled markup while JSON retains the exact
source strings. Empty sections remain visible as `None identified` so the report
structure is predictable for readers and assistive technology.

## Current interface

```python
from visiogen.analysis import (
    compose_diagram_description,
    render_description_markdown,
    write_description_bundle,
)

description = compose_diagram_description(analyzed_diagram)
markdown = render_description_markdown(description)
manifest = write_description_bundle(analyzed_diagram, output_directory)
```

The bundle writer atomically publishes `description.json`, `description.md`, and a
checksum manifest. Repeated composition of the same model produces byte-identical
artifacts.

## Acceptance

The deterministic corpus runner consumes the exact checksum-bound A3 acceptance
report. All six diagrams passed with complete object, relationship, group, legend,
limitation, visible-label, reference-number, and ambiguity coverage. The reviewed
golden report additionally covers containment, unclear direction, endpoint ambiguity,
alternatives, limitations, accessibility structure, and Markdown-injection escaping.

Exact metrics and artifact hashes are preserved in
[`../acceptance/A4_FAITHFUL_DESCRIPTION.md`](../acceptance/A4_FAITHFUL_DESCRIPTION.md).
Document-prose claim extraction and entity alignment remain Phase A5 work.
