# Visiogen Document-to-Diagram Analysis Implementation Plan

**Status:** Phases A0-A4 complete; Phase A5 next

**Date:** 2026-08-24

**Relationship to current product:** Independent of the text-to-VSDX generation pipeline

**Working feature name:** Diagram Analysis

## 1. Product definition

Visiogen currently turns a natural-language request into an editable Microsoft
Visio first draft. This plan adds a separate input-to-understanding capability:

```text
PDF or DOCX
  -> safe document inspection
  -> diagram discovery and image extraction
  -> diagram-grounded semantic and visual reconstruction
  -> faithful textual description
  -> independent extraction of document claims related to the diagram
  -> evidence-grounded consistency analysis
  -> structured findings and a human-readable report
```

The feature does **not** require a VSDX input and does not depend on the quality
or completion of the text-to-Visio workflow. The two paths share selected
infrastructure—provider calls, strict schemas, provenance, and some semantic
vocabulary—but neither path invokes the other.

The primary product outcome is an auditable analysis, not merely an AI summary.
For each discovered diagram, Visiogen should preserve what it saw, what it read,
what it inferred, what it could not determine, and exactly which evidence
supports every reported inconsistency.

## 2. Product goals

### 2.1 Required outcomes

Given a supported PDF or DOCX, Visiogen should:

1. discover diagram candidates instead of assuming every image is a diagram;
2. extract or render the diagram at adequate resolution;
3. identify visible objects, containers, connectors, arrow directions, labels,
   reference numerals, legends, annotations, and meaningful visual groupings;
4. reconstruct a source-faithful structured diagram model with visual evidence;
5. produce a readable textual description derived from that structured model;
6. identify text passages that make claims about the diagram or its components;
7. compare diagram-derived facts with text-derived claims;
8. report contradictions, omissions, ambiguity, and likely errors without
   presenting uncertain interpretations as facts;
9. cite page, image, paragraph, and region evidence for every material finding;
10. preserve exact inputs, intermediate artifacts, prompts, responses, model
    identity, timings, hashes, warnings, and final reports.

### 2.2 Intended use cases

- review an architecture diagram against its accompanying specification;
- check whether component names and reference numerals agree with prose;
- identify a connection described in text but absent from the diagram;
- identify a diagram edge whose direction contradicts the text;
- find stale labels after a document revision;
- turn a diagram into an accessible textual description;
- inventory objects and relationships in engineering or patent-oriented figures;
- flag claims that cannot be verified because the source image is unreadable.

### 2.3 Non-goals for the first release

- recreating the diagram as VSDX;
- pixel-perfect vector reconstruction;
- general-purpose document proofreading unrelated to diagrams;
- interpreting photographs, charts, equations, or UI screenshots as diagrams;
- proving the physical, scientific, legal, or engineering correctness of a design;
- filing-ready patent review or legal conclusions;
- unbounded autonomous model loops;
- silent OCR correction or silent invention of obscured labels;
- comparing unrelated diagrams across many documents;
- handwritten-diagram support;
- automatic mutation of the source PDF or DOCX.

## 3. Architectural principles

### 3.1 Keep the new path independent

Introduce a top-level `analyze` workflow rather than adding conditional behavior
to `HybridGenerationPipeline`:

```text
visiogen generate ...   # existing text -> VSDX path
visiogen analyze ...    # new document -> analysis path
```

Shared code should remain infrastructural. The new workflow must not require the
Visio template, renderer, Graphviz, Windows, or desktop Microsoft Visio.

### 3.2 Separate observation, interpretation, and comparison

The system must not ask one unconstrained prompt to inspect a whole document and
"find errors." It should use explicit stages:

1. **Document extraction:** mechanically recover pages, embedded images, native
   text, document structure, and source coordinates.
2. **Diagram observation:** inspect diagram pixels and record visible evidence.
3. **Diagram interpretation:** convert observations into objects and relations,
   retaining uncertainty and evidence references.
4. **Text claim extraction:** independently convert relevant prose into atomic
   claims, without access to the interpreted diagram where practical.
5. **Consistency analysis:** compare the two structured evidence sets.
6. **Report generation:** verbalize only validated, evidence-bound results.

This separation reduces confirmation bias and prevents nearby prose from being
mistaken for information visibly present in the diagram.

### 3.3 Preserve both semantic and visual truth

The existing `DiagramGraph` is useful for generation but is too narrow for
forensic document analysis. Analysis needs to retain:

- page-relative bounding regions;
- raw visible text and normalized text;
- OCR/model confidence and legibility;
- shape appearance and border/fill clues;
- connector paths, endpoints, arrowheads, and uncertainty;
- label-to-object and label-to-connector attachment;
- container and spatial grouping evidence;
- legends and symbol definitions;
- evidence provenance for every observation;
- alternative interpretations when the image is ambiguous.

The analysis model may expose a compatibility projection into `DiagramGraph`,
but `DiagramGraph` must not be the authoritative evidence record.

### 3.4 Code owns mechanical facts; AI owns visual judgment

Application code should own:

- file type and signature checks;
- archive limits and safe extraction;
- PDF page and DOCX relationship enumeration;
- deterministic text extraction where available;
- page/image dimensions and coordinate normalization;
- hashes and artifact identity;
- schema and reference validation;
- evidence-reference validation;
- deterministic comparison rules for exact normalized facts;
- report consistency checks.

The multimodal model should own:

- diagram-vs-non-diagram classification;
- object and connector recognition;
- difficult label association;
- semantic type interpretation;
- visual grouping and hierarchy;
- ambiguity-aware reconstruction;
- semantic equivalence judgments not reducible to exact matching.

### 3.5 Never collapse uncertainty into absence

`not visible`, `not present`, `illegible`, `occluded`, and `not analyzed` are
different states. The schemas and report must preserve these distinctions.

### 3.6 Findings require evidence from both sides

A contradiction normally requires:

- at least one diagram evidence reference;
- at least one text evidence reference;
- an explicit normalized proposition from each source;
- a comparison explanation;
- a confidence level and uncertainty note.

An exception is a document-internal diagram defect such as a duplicate reference
number or a connector ending in empty space. Such findings still require diagram
evidence and must be categorized separately from text/diagram contradictions.

## 4. Proposed package structure

Keep analysis-specific code in its own package to avoid overloading current
generation concepts:

```text
src/visiogen/
  analysis/
    __init__.py
    models.py                 # evidence, diagram, claims, findings, result
    pipeline.py               # document-analysis orchestration
    validation.py             # hard cross-reference and evidence checks
    description.py            # deterministic report/description composition
    comparison.py             # deterministic and model-assisted comparison
    prompts.py                # versioned logical prompts
    artifacts.py              # atomic provenance writer and manifest
    selection.py              # candidate ranking and explicit selection
  documents/
    __init__.py
    models.py                 # pages, images, paragraphs, source locations
    sniffing.py               # signature/type validation
    pdf.py                    # PDF inspection, rendering, text blocks
    docx.py                   # safe OOXML inspection and media relationships
    rendering.py              # injectable page-rendering boundaries
    safety.py                 # limits, archive policy, path validation
  providers/
    multimodal.py             # capability protocol, not provider policy
```

Existing `providers/codex_cli.py` can supply the first structured multimodal
transport after small generic improvements. Analysis orchestration should depend
on protocols rather than Codex directly.

## 5. End-to-end runtime design

### Stage A — Input admission and immutable source identity

Inputs:

- one local `.pdf` or `.docx` file;
- an empty artifact directory;
- optional diagram selection controls;
- explicit provider/model and limits.

Actions:

1. reject symbolic links unless a future explicit policy permits them;
2. inspect magic bytes and container structure, not only the extension;
3. calculate SHA-256 before processing;
4. copy the source into a private staging area or access it read-only;
5. record source size, media type, page count, and warnings;
6. enforce configured limits before expensive model calls.

The original source should not be duplicated into user-visible artifacts by
default if privacy is a concern. The manifest can bind to its absolute input path
and hash. An explicit `--copy-source` option can preserve it when desired.

### Stage B — Safe document decomposition

#### PDF path

Extract:

- page count and page boxes;
- native text spans/blocks with page coordinates where available;
- embedded raster images when reliably recoverable;
- full-page renders for visual discovery and for vector diagrams;
- rotation and render-scale metadata.

Do not assume embedded-image extraction is enough. Many PDF diagrams are vector
content, a mixture of vector and raster objects, or fragmented into several image
objects. Full-page rendering is the universal visual fallback.

Password-protected PDFs should fail with a typed error in the MVP. Active content,
attachments, and external links should never be opened or followed.

#### DOCX path

Mechanically inspect OOXML without executing Office:

- paragraphs, runs, tables, headings, captions, footnotes, and endnotes;
- relationship IDs and embedded media;
- drawing anchors and approximate document order;
- page/section hints when present;
- alt text, title, description, and captions;
- headers and footers as separately labeled text regions;
- grouped DrawingML/SmartArt/vector content when recoverable.

Embedded images should be extracted directly at original resolution. However,
DOCX page layout is not fully determined by OOXML alone. Diagrams made from Word
shapes, SmartArt, text boxes, or grouped drawing objects may require page rendering.
The architecture must therefore support two modes:

- **portable extraction mode:** embedded media plus OOXML text/order; works without
  Microsoft Word or LibreOffice and reports layout limitations;
- **rendered mode:** convert/render pages through an explicitly configured Office
  or LibreOffice boundary, then analyze page images as well.

The MVP may begin with portable mode for embedded raster diagrams and make rendered
DOCX pages a later acceptance gate. It must never imply that unrendered Word shapes
were inspected.

#### Common normalized document model

Both readers produce a `DocumentSnapshot` containing:

- `source_id` and source hash;
- ordered `DocumentPage` records when page identity exists;
- `TextBlock` records with stable IDs and source locations;
- `VisualAsset` records for page renders and embedded media;
- mappings between assets, pages, captions, anchors, and nearby text;
- extraction warnings and coverage status.

### Stage C — Diagram candidate discovery

Candidate discovery should use cheap mechanical heuristics first, followed by a
bounded multimodal classification call when needed.

Candidate sources:

- embedded images above minimum dimensions;
- page render regions near captions such as Figure, Fig., Diagram, Architecture,
  Flow, Schematic, or System;
- full pages with high graphical content and limited prose;
- DOCX drawing anchors and alt text;
- manually selected pages or image IDs.

Each candidate records:

- candidate ID;
- asset and page reference;
- crop rectangle in normalized page coordinates;
- candidate source (`embedded_image`, `page_crop`, `full_page`, `docx_drawing`);
- caption/alt-text references;
- discovery reason and score;
- duplicate-family ID when embedded and rendered versions show the same diagram.

The classifier should label candidates as:

- `diagram`;
- `chart`;
- `table`;
- `photograph`;
- `ui_screenshot`;
- `equation`;
- `decorative`;
- `unknown`.

Only `diagram` candidates proceed automatically. `unknown` remains reviewable and
must not be silently discarded.

For the initial CLI, support deterministic selection:

```text
--page 4
--candidate figure_2
--all-diagrams
```

If multiple candidates exist and no selection is given, analyze all candidates up
to a configurable maximum and state that coverage in the manifest.

### Stage D — Image preparation

Prepare model inputs without altering the evidentiary original:

- preserve the original extracted/rasterized asset;
- normalize rotation based on document metadata;
- generate a lossless PNG working image;
- render at a target effective resolution with a maximum pixel budget;
- create overlapping tiles for dense or very large diagrams;
- retain tile-to-source coordinate transforms;
- optionally create contrast-enhanced derivatives, clearly marked as derivatives;
- never overwrite the original or hide preprocessing.

Tiling is important because downscaling a detailed schematic can erase arrowheads,
small reference numerals, and connector labels. The provider should receive an
overview plus ordered tiles. The result schema must use normalized source-image
coordinates, not tile-local coordinates.

### Stage E — Diagram-grounded observation

The first substantive model call should see only the diagram image, its crop/page
identity, and minimal non-semantic metadata. It should not see nearby explanatory
prose. Captions and alt text may be passed in a later interpretation call, but must
not contaminate the record of what is visibly present.

The observation result should contain:

- all visible text regions, including uncertain OCR alternatives;
- candidate objects and their bounding boxes;
- containers and visual grouping regions;
- connector paths or endpoint regions;
- arrowhead observations at either endpoint;
- connector/object label associations;
- legends, keys, notes, and callouts;
- line styles, colors, fills, borders, and repeated symbol families when meaningful;
- reading-order and flow-orientation clues;
- legibility/occlusion warnings;
- evidence IDs bound to regions.

The observation prompt should favor completeness over semantic elegance. It should
not guess hidden endpoints or convert uncertain visual marks into definitive edges.

### Stage F — Structured semantic reconstruction

A separate schema-constrained call converts visible observations into a semantic
model. It may see the source image again plus the validated observations. It should
return:

#### Diagram metadata

- title, if visibly present;
- family (`flowchart`, `system_block`, `component_schematic`, `state_machine`,
  `network`, `data_flow`, `sequence_like`, `unknown`);
- orientation and reading order;
- page/candidate identity;
- overall interpretation confidence;
- explicit limitations.

#### Objects

- stable analysis ID;
- visible label exactly as seen;
- normalized label for comparison;
- semantic type and visual shape class;
- reference numeral(s);
- parent/container ID;
- source bounding box;
- notes/callouts attached to the object;
- evidence references;
- confidence and alternative interpretations.

#### Relationships

- stable edge ID;
- source and target object IDs when supported;
- endpoint certainty when one end is ambiguous;
- direction (`forward`, `reverse`, `bidirectional`, `none`, `unclear`);
- semantic relation (`flow`, `data`, `control`, `power`, `communication`,
  `mechanical`, `association`, `unknown`);
- visible label and normalized label;
- line style and arrowhead evidence;
- evidence references;
- confidence and alternatives.

#### Visual structure

- groups, lanes, layers, zones, and containment;
- legend symbol mappings;
- emphasized/de-emphasized elements;
- repeated patterns;
- disconnected or dangling elements;
- apparent start/end points.

Hard validation then checks IDs, references, coordinates, parent cycles, evidence
references, and connector endpoint consistency. One schema/structure repair is
permitted. Repair may correct formatting and references but must not invent visual
evidence. If the reconstructed model remains invalid, analysis fails for that
candidate while preserving the raw response and error.

### Stage G — Deterministic description generation

The default textual description should be generated primarily from the validated
structured model rather than by another free-form vision call. This ensures that
the prose and JSON cannot quietly disagree.

Recommended report order:

1. diagram identity, type, and purpose if evident;
2. overall layout and reading direction;
3. containers/groups and their contents;
4. object inventory with exact visible labels and reference numerals;
5. relationships, directions, and connector labels;
6. notes, legends, and callouts;
7. disconnected or ambiguous elements;
8. explicit visibility and interpretation limitations.

An optional language-polish call may improve readability, but code must validate
that it does not introduce IDs, labels, relationships, or claims absent from the
structured model. The MVP should prefer deterministic templates.

### Stage H — Independent document-claim extraction

Relevant text selection occurs before claim extraction. Candidate passages include:

- the caption;
- paragraphs before and after the figure anchor;
- paragraphs that mention the figure number;
- paragraphs containing exact or fuzzy matches to visible labels/reference numbers;
- table cells, footnotes, and endnotes linked to those passages;
- an optional user-specified text range.

Preserve document order and source coordinates. Do not send the entire document by
default; doing so increases cost, prompt-injection exposure, and irrelevant claims.

The claim extractor should see the selected prose and document locations, but not
the diagram interpretation on its first pass. It returns atomic `DocumentClaim`
records such as:

- object existence or non-existence;
- object naming or alias;
- object type/role;
- containment;
- source-target relationship;
- relationship direction;
- relationship type;
- branch condition;
- cardinality or count;
- reference-number mapping;
- sequence/order;
- attribute or state;
- explicit figure-level title/purpose.

Each claim includes:

- exact supporting text span within a short bounded excerpt;
- paragraph/page/block IDs;
- normalized subject, predicate, and object/value;
- modality (`asserted`, `required`, `possible`, `example`, `negated`, `unknown`);
- scope and qualifiers;
- whether it refers to the current figure;
- confidence and ambiguity.

Requirements, possibilities, examples, and negative claims must not be compared as
though they were all unconditional present-tense facts.

### Stage I — Entity alignment

Before comparing facts, align text entities with diagram objects. Use a layered
approach:

1. exact reference-numeral match;
2. exact normalized label match;
3. explicit alias/apposition from prose;
4. conservative fuzzy match;
5. model-assisted semantic alignment with evidence and confidence;
6. unresolved rather than forced alignment.

Return an `EntityAlignment` record with match method, score, supporting evidence,
and alternatives. Do not use a single global string-similarity threshold for all
domains. Short labels such as `A`, `I/O`, `DB`, or `1` need stricter handling.

### Stage J — Consistency and defect analysis

Run deterministic checks first:

#### Diagram-internal checks

- duplicate reference numerals assigned to different objects;
- one object assigned conflicting visible labels;
- dangling connector endpoints;
- ambiguous arrow direction;
- connector label unattached to any connector;
- child apparently outside its labeled container;
- legend symbol used inconsistently;
- unreadable label that blocks verification;
- isolated object that appears intended to participate in the flow.

Some are warnings, not errors. Visual overlap or proximity alone must not prove
containment or connectivity.

#### Text/diagram checks

- claimed object missing from diagram;
- diagram object omitted from an exhaustive textual inventory;
- label mismatch;
- reference-number mismatch;
- claimed relationship missing;
- extra diagram relationship contradicting an exhaustive claim;
- source/target reversal;
- direction mismatch;
- relationship-type mismatch;
- containment mismatch;
- sequence or branch mismatch;
- count/cardinality mismatch;
- diagram title/caption mismatch;
- terminology inconsistency that is likely harmless but reviewable.

Absence findings need special discipline. Text mentioning only some components is
not evidence that unmentioned diagram components are errors. An omission can be
flagged only when the text claims completeness, the context clearly enumerates the
figure, or the user selects a strict coverage mode.

#### Model-assisted semantic adjudication

Use a bounded structured model call only for comparisons deterministic rules cannot
settle—for example aliases, domain-specific relationship equivalence, or qualifiers.
The adjudicator receives only the two candidate propositions and their evidence,
not an invitation to reanalyze the entire document.

Finding outcomes:

- `confirmed_consistent`;
- `confirmed_contradiction`;
- `probable_contradiction`;
- `possible_omission`;
- `terminology_difference`;
- `diagram_internal_warning`;
- `unverifiable`;
- `needs_human_review`.

Every finding includes severity, confidence, evidence from each applicable side,
a concise explanation, and a suggested human verification action. It should not
automatically prescribe changes when the authoritative source is unknown.

### Stage K — Final report and machine-readable bundle

Produce both:

- `analysis.json`: complete validated machine-readable result;
- `report.md`: accessible description, findings, evidence locations, and limits.

The report should clearly distinguish:

- observed visible facts;
- semantic interpretations;
- textual claims;
- confirmed contradictions;
- uncertain or unverifiable issues;
- analysis coverage and skipped content.

## 6. Core data contracts

The precise Pydantic definitions should be implemented test-first. The conceptual
contracts are:

```text
SourceLocation
  source_id
  page_number?
  block_id?
  paragraph_index?
  relationship_id?
  asset_id?
  bbox?                 # normalized 0..1 coordinates

Evidence
  id
  kind                  # image_region, native_text, caption, alt_text, metadata
  location
  exact_text?
  derivative_id?
  confidence

VisualObservation
  id
  kind
  bbox/path
  visible_text?
  properties
  evidence_ids
  confidence
  alternatives

AnalyzedObject
  id
  visible_label
  normalized_label
  semantic_type
  visual_shape
  reference_numbers
  parent_id?
  bbox
  evidence_ids
  confidence
  alternatives

AnalyzedRelationship
  id
  source_id?
  target_id?
  direction
  relation
  visible_label?
  path?
  evidence_ids
  confidence
  alternatives

AnalyzedDiagram
  candidate_id
  title?
  family
  orientation
  objects
  relationships
  groups
  legends
  limitations
  confidence

DocumentClaim
  id
  subject
  predicate
  object_or_value
  modality
  qualifiers
  refers_to_candidate
  evidence_ids
  confidence

ConsistencyFinding
  id
  category
  status
  severity
  diagram_fact
  text_claim?
  diagram_evidence_ids
  text_evidence_ids
  explanation
  confidence
  review_action
```

Schema rules:

- strict `extra="forbid"` for all model output;
- no NaN/infinity;
- normalized bounding coordinates in `[0, 1]`;
- stable IDs unique within the analysis;
- all evidence and object references must resolve;
- exact visible text must remain separate from normalized comparison text;
- every interpreted object and relationship must reference visual evidence;
- every text claim must reference native or OCR text evidence;
- every contradiction must cite both sides unless explicitly diagram-internal;
- confidence is categorical or rigorously defined, not an arbitrary unexplained
  floating-point number.

Recommended confidence values are `high`, `medium`, `low`, and `unknown`, with
prompt-level definitions and deterministic downgrades for illegibility or unresolved
endpoints.

## 7. CLI and user-facing contract

Proposed MVP command:

```bash
uv run visiogen analyze \
  --input design-spec.pdf \
  --output artifacts/review/report.md \
  --artifact-dir artifacts/review/evidence \
  --model gpt-5.6-sol
```

Useful options:

```text
--page N                    analyze candidates on one page
--candidate ID              analyze one discovered candidate
--all-diagrams              analyze all candidates within configured limits
--strict-coverage           allow exhaustive-inventory omission findings
--no-consistency-check      produce diagram descriptions only
--max-pages N
--max-diagrams N
--render-dpi N
--docx-renderer portable|libreoffice|word
--keep-source-copy
```

The command must refuse a non-empty artifact directory, symbolic-link collisions,
reserved filenames, and output paths that overlap private working files. Partial
multi-diagram results should be explicit: one failed candidate must not be silently
omitted from a successful document report.

Exit behavior should distinguish:

- successful analysis with no contradictions;
- successful analysis with review findings;
- partial candidate failure;
- unsupported/encrypted/unsafe input;
- provider failure;
- invalid provider output.

Findings should not make the command fail by default. A later CI-oriented option
may map configured severity/status thresholds to exit codes.

## 8. Provenance and artifact layout

Suggested bundle:

```text
evidence/
  manifest.json
  00-source-metadata.json
  01-document-snapshot.json
  02-native-text.json
  03-candidates.json
  assets/
    page-0001.png
    candidate-001-original.png
    candidate-001-overview.png
    candidate-001-tile-*.png
  candidate-001/
    10-observation-system-prompt.txt
    11-observation-user-prompt.txt
    12-observation-provider-prompt.txt
    13-observation-response.json
    14-validated-observations.json
    20-reconstruction-system-prompt.txt
    21-reconstruction-user-prompt.txt
    22-reconstruction-provider-prompt.txt
    23-reconstruction-response.json
    24-analyzed-diagram.json
    25-description.md
    30-selected-text-blocks.json
    31-claim-prompt.txt
    32-claim-provider-prompt.txt
    33-claim-response.json
    34-document-claims.json
    40-alignments.json
    41-comparison-input.json
    42-adjudication-response.json
    43-findings.json
  analysis.json
  report.md
```

The manifest records:

- source hash, size, type, and filename;
- source revision and worktree cleanliness when run from a checkout;
- application version;
- provider/model per stage;
- logical and exact transport prompt hashes;
- schema hashes;
- page render and image hashes;
- renderer/tool identity and versions;
- candidate coverage and exclusions;
- every warning, retry, repair, and partial failure;
- total and per-stage timing;
- final `analysis.json` and `report.md` hashes.

Raw extracted text and source images may contain sensitive data. Artifact retention
should be explicit in documentation, directory permissions should default to
private, and logs must not print document content.

## 9. Security and privacy threat model

### 9.1 Untrusted document containers

PDF and DOCX are untrusted inputs. Guard against:

- ZIP bombs and extreme compression ratios;
- archive path traversal;
- oversized entries or image dimensions;
- excessive page counts or object counts;
- malformed XML and entity expansion;
- external OOXML relationships;
- macros, OLE objects, and embedded packages;
- PDF attachments, JavaScript, actions, and external links;
- renderer hangs and crashes;
- decompression and rasterization denial of service.

Use explicit limits for file bytes, uncompressed bytes, ZIP members, page count,
pixels per image, total rendered pixels, XML depth/size, diagrams per document, and
model calls. Run optional external renderers behind timeouts in private temporary
directories with no network and minimal environment.

### 9.2 Prompt injection inside documents

Text inside diagrams and documents is data, even when it says "ignore previous
instructions" or asks the model to access files. Prompts must state that source
content is untrusted evidence and cannot change the task, schema, tool permissions,
or requested scope.

The Codex adapter already uses an ephemeral, read-only workspace, ignores user
rules/config, and passes a narrow environment. Retain those protections. Copy only
the required images into the isolated workspace. Do not give the model the original
document path, unrelated files, or shell objectives.

### 9.3 Privacy

- no provider fallback without user configuration;
- record which pages/images/text were sent to which provider;
- support a future local-only provider mode, but do not claim parity without tests;
- avoid sending irrelevant document pages;
- redact credentials from errors and manifests;
- document that provider calls may transmit selected content externally;
- do not include raw document content in terminal output by default.

## 10. Error taxonomy and honest degradation

Typed errors should include:

- `UnsupportedDocumentError`;
- `DocumentTypeMismatchError`;
- `EncryptedDocumentError`;
- `UnsafeDocumentError`;
- `DocumentLimitExceededError`;
- `DocumentExtractionError`;
- `DocumentRenderError`;
- `NoDiagramCandidateError`;
- `AmbiguousDiagramSelectionError`;
- `DiagramObservationError`;
- `DiagramReconstructionError`;
- `ClaimExtractionError`;
- `EvidenceValidationError`;
- `ComparisonError`.

Degradation must be visible. Examples:

- native text unavailable -> OCR-derived text marked as such;
- DOCX pages not rendered -> embedded images analyzed, Word drawing coverage pending;
- arrowhead illegible -> direction `unclear`, not `none`;
- candidate crop uncertain -> analyze full page and record possible surrounding noise;
- text alignment unresolved -> finding `unverifiable`, not contradiction;
- one candidate fails -> partial document result with failure record.

## 11. Testing strategy

### 11.1 Unit and contract tests

Test without model calls:

- PDF/DOCX signature validation;
- safe OOXML member enumeration and archive limits;
- PDF page/text/image metadata normalization;
- DOCX paragraph, caption, relationship, and media extraction;
- coordinate transforms for pages, crops, and tiles;
- candidate deduplication;
- schema strictness and invalid reference rejection;
- evidence-reference validation;
- deterministic description generation;
- entity normalization and conservative matching;
- comparison rules including modality and exhaustive-scope behavior;
- atomic artifact writes and collision rejection;
- manifest hashes and partial-failure reporting;
- prompt construction and source-content delimiting;
- provider transport isolation and multi-image ordering.

### 11.2 Synthetic visual fixtures

Create small, programmatically controlled diagram images covering:

- linear flow;
- branching decision with Yes/No labels;
- bidirectional system relationship;
- nested subsystem/container;
- reference numerals and callouts;
- dashed vs solid connectors;
- connector crossing without connection;
- dangling connector;
- duplicate labels/reference numerals;
- ambiguous or low-resolution arrowhead;
- disconnected object;
- legend-driven symbols;
- rotated page;
- dense diagram requiring tiles.

Pair each image with ground-truth observations, semantic graph, and descriptions.
These fixtures prove schema and evaluation machinery, not real model quality.

### 11.3 Document fixtures

Build reviewed PDF and DOCX fixtures for:

- one embedded raster diagram plus native nearby text;
- vector PDF diagram requiring page rendering;
- DOCX embedded image with caption and cross-reference;
- DOCX with table-contained image;
- DOCX with header/footer noise;
- DOCX with Word shapes/SmartArt that portable mode cannot fully inspect;
- scanned PDF requiring visual/OCR text extraction;
- multiple diagrams on one page;
- repeated diagram embedded at different resolutions;
- non-diagram images that must be excluded;
- encrypted PDF;
- malformed/truncated inputs;
- external relationships and embedded-object warnings;
- compressed archive and pixel-limit rejection.

### 11.4 Consistency fixture matrix

For each representative diagram, create text variants containing exactly one
controlled condition:

- fully consistent;
- object name mismatch;
- reference-number mismatch;
- missing claimed component;
- extra diagram component with non-exhaustive prose (must not flag as error);
- extra diagram component with exhaustive inventory (may flag omission);
- reversed edge;
- wrong relationship type;
- wrong containment;
- incorrect sequence;
- modal statement (`may connect`) vs assertion (`connects`);
- negated statement;
- alias and abbreviation;
- intentionally ambiguous wording;
- unreadable diagram label.

### 11.5 Real-provider acceptance

Fake responses can prove transport, parsing, and comparison plumbing only. A real
multimodal model acceptance corpus should include at least:

1. clean flowchart in a native-text PDF;
2. system architecture embedded in DOCX;
3. dense component schematic with reference numerals;
4. vector PDF figure;
5. low-quality scanned figure with explicit uncertainty;
6. document containing multiple diagram and non-diagram images;
7. adversarial document text containing prompt-injection instructions.

For each case preserve exact provider evidence and score separately:

- candidate discovery precision/recall;
- visible-label transcription accuracy;
- object precision/recall;
- relationship endpoint accuracy;
- direction accuracy;
- containment accuracy;
- reference-number accuracy;
- claim extraction accuracy;
- entity alignment accuracy;
- contradiction precision/recall;
- unsupported-claim or hallucination count;
- evidence-location validity;
- uncertainty calibration.

### 11.6 Human review rubric

Two passes are useful:

- **diagram review:** compare `analyzed-diagram.json` and description against the
  source image without reading the document prose;
- **consistency review:** compare findings against both diagram and cited passages.

Reviewers should label false positives, false negatives, unsupported inference,
wrong evidence, overconfidence, and harmless terminology differences.

## 12. Acceptance thresholds

Exact thresholds should be set after a pilot, but release gates must prioritize
precision and evidence validity over the number of findings.

Recommended MVP gates:

1. 100% schema/reference validity for completed analyses.
2. 100% of reported contradictions cite valid diagram and text evidence.
3. Zero invented labels or reference numerals in the reviewed acceptance corpus.
4. Zero forced source/target direction when direction is visibly unclear.
5. No omission error from non-exhaustive prose in the controlled matrix.
6. At least 95% exact visible-label accuracy on clean inputs.
7. At least 90% object and relationship F1 on clean, in-scope diagrams.
8. At least 90% precision for `confirmed_contradiction` findings.
9. Every degraded or skipped source modality is visible in the final report.
10. Prompt-injection fixtures cannot change schema, access unrelated files, or
    suppress required provenance.

Low-quality scans should not be judged by clean-input recall targets. Their gate is
honest uncertainty: the system must avoid confident false claims and identify what
cannot be verified.

## 13. Phased implementation plan

The phases are ordered as vertical risk reduction, not merely by file type.

### Phase A0 — Contract decisions and fixture charter

**Status:** Complete. The frozen decisions and fixture charter are recorded in
[`../../analysis/MVP_CONTRACT.md`](../../analysis/MVP_CONTRACT.md).

**Goal:** Freeze terminology, evidence rules, supported MVP document subset, and
evaluation method before building provider prompts.

Tasks:

- adopt this plan or revise its product boundaries;
- choose whether MVP DOCX support is embedded images only or includes rendered pages;
- define default document/page/image limits;
- define confidence semantics;
- define figure selection behavior for multiple candidates;
- create the controlled consistency matrix and reviewer rubric;
- check in only redistributable or locally generated fixtures.

**Gate:** Each planned finding category has a positive, negative, and ambiguous test
case. Unsupported DOCX/PDF constructs have explicit expected behavior.

### Phase A1 — Document safety and normalized extraction

**Status:** Complete. The implemented boundary and runtime requirements are recorded
in [`../../analysis/DOCUMENT_INGESTION.md`](../../analysis/DOCUMENT_INGESTION.md).

**Goal:** Turn PDF and DOCX inputs into a deterministic `DocumentSnapshot` without
using AI.

Files:

- create `src/visiogen/documents/*`;
- create `tests/documents/*`;
- add narrowly selected PDF/DOCX dependencies;
- document third-party renderer requirements separately from core parsing.

Tasks:

- signature sniffing and typed input errors;
- safe PDF inspection and page rendering abstraction;
- safe DOCX OOXML/media/text extraction;
- source locations and stable block/asset IDs;
- explicit limits and timeouts;
- atomic snapshot and asset artifact writer.

**Gate:** Reviewed fixtures produce stable snapshots and assets. Malformed, encrypted,
oversized, external-resource, and archive-abuse cases fail or warn exactly as specified.

**Suggested commit:** `Add safe PDF and DOCX document extraction`

### Phase A2 — Diagram discovery and image preparation

**Status:** Complete. Candidate contracts, exact and conservative perceptual
deduplication, mechanical and structured multimodal classification, explicit selection,
bounded crop/overview/tile preparation, and the reviewed corpus are implemented. The
real-provider quality gate passed and its evidence is preserved in
[`../../acceptance/A2_DIAGRAM_DISCOVERY.md`](../../acceptance/A2_DIAGRAM_DISCOVERY.md).

**Goal:** Reliably find and prepare candidate diagrams while excluding obvious
photographs, charts, and decorative assets.

Files:

- create `analysis/selection.py` and candidate models;
- create image preparation/crop/tiling utilities;
- extend generic multimodal provider protocol as needed;
- add candidate and non-candidate fixtures.

Tasks:

- mechanical candidate enumeration;
- structured candidate classification;
- embedded-image/page-render deduplication;
- crop and tile transforms;
- CLI discovery/selection flags;
- candidate coverage reporting.

**Gate:** Candidate discovery meets an agreed precision/recall score on the reviewed
fixture set, and every accepted/ignored candidate has a recorded reason.

**Suggested commit:** `Discover and prepare document diagram candidates`

### Phase A3 — Visual observation and semantic reconstruction

**Status:** Complete. Strict observation and semantic models, deterministic
tile-to-source transforms, hard evidence/reference/anti-invention validation,
overview-plus-tiles calls, one bounded repair per stage, complete call traces, and
the four-call candidate budget are implemented. The six-case clean real-provider
quality gate passed and its evidence is preserved in
[`../../acceptance/A3_VISUAL_SEMANTICS.md`](../../acceptance/A3_VISUAL_SEMANTICS.md).

**Goal:** Produce a strict, evidence-grounded diagram model from images.

Files:

- create `analysis/models.py`, `analysis/prompts.py`, and `analysis/validation.py`;
- add observation and reconstruction workflows;
- add fake-runner contract tests and real-provider evidence runner.

Tasks:

- observation schema and prompt;
- overview-plus-tiles input support;
- reconstruction schema and prompt;
- one bounded structural repair;
- evidence and cross-reference validation;
- explicit alternative/uncertainty support;
- compatibility projection to `DiagramGraph` only if useful.

**Gate:** Real-provider clean-diagram corpus meets initial label/object/edge/reference
accuracy targets with no invented labels. Ambiguous fixtures produce uncertainty
rather than fabricated certainty.

**Suggested commit:** `Extract evidence-grounded diagram semantics from images`

### Phase A4 — Faithful textual description

**Status:** Complete. Deterministic traceable JSON and accessible Markdown composition,
canonical section ordering, exact visible-label/reference rendering, relationship and
containment narration, ambiguity/disconnection/limitation reporting, hard coverage
validation, atomic artifacts, golden examples, and the checksum-bound six-case A3
acceptance corpus are implemented. The gate passed and its evidence is preserved in
[`../../acceptance/A4_FAITHFUL_DESCRIPTION.md`](../../acceptance/A4_FAITHFUL_DESCRIPTION.md).

**Goal:** Produce readable, comprehensive descriptions that remain mechanically
traceable to the analyzed model.

Files:

- create `analysis/description.py`;
- add golden description-structure tests;
- add accessibility-oriented report examples.

Tasks:

- deterministic description ordering;
- exact visible label/reference rendering;
- relationship and containment narration;
- ambiguity and limitation section;
- stable Markdown and JSON outputs.

**Gate:** Every described object/relationship resolves to the structured model;
every high-impact model element appears in the description; no unsupported prose is
introduced.

**Suggested commit:** `Describe analyzed diagrams from validated evidence`

### Phase A5 — Text claim extraction and entity alignment

**Goal:** Independently turn nearby diagram-related prose into evidence-bound atomic
claims and align its entities conservatively.

Files:

- add text relevance selector and claim models/workflow;
- add entity alignment logic;
- add modality, negation, alias, and scope fixtures.

Tasks:

- caption/cross-reference/proximity passage selection;
- claim schema and strict extraction prompt;
- evidence span validation;
- exact/reference/alias/fuzzy alignment layers;
- unresolved and alternative alignment support.

**Gate:** Claims never cite text outside selected source blocks; controlled modality
and negation cases are classified correctly; ambiguous entities remain unresolved.

**Suggested commit:** `Extract and align diagram-related document claims`

### Phase A6 — Consistency engine and findings

**Goal:** Compare diagram facts and text claims with high precision and produce
auditable findings.

Files:

- create `analysis/comparison.py`;
- implement finding validators and report sections;
- add the full consistency matrix.

Tasks:

- deterministic internal and cross-source checks;
- exhaustive-scope rules for omissions;
- bounded semantic adjudication;
- severity/status/confidence policy;
- evidence-complete findings;
- suggested human review actions;
- no automatic assumption about which source is authoritative.

**Gate:** Controlled contradiction matrix meets precision target, produces no known
non-exhaustive omission false positives, and every finding passes evidence validation.

**Suggested commit:** `Compare diagram evidence with document claims`

### Phase A7 — Public analysis pipeline, CLI, and provenance

**Goal:** Compose the production vertical slice without coupling it to generation.

Files:

- create `analysis/pipeline.py` and `analysis/artifacts.py`;
- extend `cli.py` with the `analyze` command;
- add pipeline, CLI, artifact, partial-failure, and security tests;
- update README and system overview.

Tasks:

- complete orchestration and dependency injection;
- safe output/evidence directory preparation;
- per-stage prompt/response persistence;
- source/model/schema/tool hashes;
- multi-candidate aggregation;
- Markdown and JSON report generation;
- explicit partial-result and exit behavior.

**Gate:** A fresh PDF and DOCX travel through the real provider and produce complete,
hash-bound, reviewable bundles without invoking any VSDX generation code.

**Suggested commit:** `Compose document to diagram analysis pipeline`

### Phase A8 — Real acceptance, hardening, and release decision

**Goal:** Establish honest supported scope and measured quality.

Tasks:

- run the full real-provider corpus from immutable source;
- perform blinded diagram review and consistency review;
- calculate metrics and document failures;
- tune prompts only against a development subset;
- rerun a held-out corpus;
- test adversarial documents and resource limits;
- define which DOCX rendering modes are accepted on each platform;
- publish known limitations and model/provider identity.

**Gate:** All security, provenance, evidence, and agreed quality thresholds pass on
held-out cases. Failures are preserved rather than overwritten.

**Suggested commit:** `Validate document diagram analysis`

## 14. Dependency strategy

Select dependencies during A1 using small spikes rather than committing the design
to a library name now. Required capabilities are:

- PDF metadata/text extraction with coordinates;
- deterministic PDF rasterization at controlled resolution;
- safe OOXML ZIP/XML inspection;
- image metadata and lossless conversion;
- optional OCR only when native text is absent or diagram labels require it;
- optional DOCX page rendering through an external application boundary.

Avoid making a heavyweight office suite a mandatory Python dependency. External
renderers should be optional capabilities detected at runtime. Dependency licenses,
native binaries, platform support, reproducibility, and malformed-input behavior
must be recorded in the spike decision.

The AI vision model itself may transcribe diagram labels, but deterministic OCR can
provide an independent candidate reading and confidence signal. It should not become
an invisible authority that overwrites what the model saw.

## 15. Design decisions that should remain explicit

### One model call vs staged calls

Use staged calls despite higher latency. Observation, reconstruction, claims, and
comparison have different schemas and contamination risks. Cache stage results by
source/crop/prompt/schema/provider/model hash to control repeated cost later.

### Embedded image vs rendered page

Prefer the embedded original for label accuracy when it represents the complete
diagram. Keep the rendered page for location/caption context and for vector or
composite diagrams. Do not treat them as separate diagrams when they are duplicates.

### Caption/alt text as truth

Treat captions and alt text as document claims, not pixels visibly present in the
diagram. They may guide selection but cannot fill missing visual labels silently.

### OCR vs multimodal model text

Preserve both readings when available. Exact agreement raises confidence; conflict
creates an alternative or review warning. Neither source should silently overwrite
the other.

### Which side is authoritative

The system usually cannot know whether diagram or prose is correct. Report a
cross-source inconsistency and the competing evidence. Only use terms such as
"diagram error" when a rule is diagram-internal or the user explicitly designates
an authoritative source.

### Multi-diagram documents

Model each candidate independently, then aggregate. Cross-figure entity alignment
and evolution/version comparison are future features, not implicit MVP behavior.

## 16. Deferred extensions

- VSDX reconstruction from the analyzed diagram model;
- cross-document and cross-version diagram comparison;
- multi-page logical diagrams split across figures;
- user corrections that become reusable extraction hints;
- domain-specific symbol packs for electrical, UML, BPMN, P&ID, or networking;
- handwritten whiteboard diagrams;
- table/chart consistency analysis;
- automatic redlining or comments inserted into DOCX/PDF;
- interactive evidence viewer with clickable bounding boxes;
- provider ensembles or candidate voting;
- local OCR/vision parity mode;
- CI policy configuration and machine-readable SARIF-like findings.

## 17. Definition of done for the first useful release

The feature is done when a user can give Visiogen a supported PDF or DOCX and receive:

1. an identified and preserved diagram image;
2. a complete structured inventory of visible objects, labels, reference numerals,
   containers, and relationships within the accepted diagram classes;
3. a faithful textual description generated from that validated inventory;
4. independently extracted, source-located document claims;
5. high-precision consistency findings with evidence from both modalities;
6. explicit uncertainty and coverage limitations;
7. a machine-readable analysis and readable Markdown report;
8. complete provider, prompt, artifact, source, and checksum provenance;
9. passing unit/security tests and preserved real-provider acceptance evidence;
10. no dependency on Microsoft Visio or the text-to-VSDX generation pipeline.

Until real-provider and human-reviewed acceptance is complete, the feature should be
described as implemented or experimental—not as reliably understanding arbitrary
technical diagrams.
