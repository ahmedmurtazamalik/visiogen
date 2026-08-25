# Document Analysis MVP Contract

**Status:** Frozen for Phase A1

**Date:** 2026-08-24

This document closes Phase A0. It fixes the first-release boundaries that must
remain stable while deterministic document ingestion is implemented. Changes to
these decisions require an explicit plan update and corresponding fixture changes.

## Supported input scope

### PDF

The MVP supports ordinary, unencrypted PDFs. A complete PDF implementation must
recover native text with page coordinates when available and render every admitted
page through a bounded PDF renderer. Embedded-image extraction is supplemental;
it cannot replace page rendering because diagrams may be vector or composite.

Encrypted PDFs, portfolios, attachments, JavaScript, launch actions, and external
resources are not opened. An encrypted PDF fails with a typed error rather than an
interactive password prompt.

### DOCX

Portable DOCX mode supports native OOXML text, tables, captions, alt text,
relationships, and embedded raster media. It does not claim to inspect Word shapes,
SmartArt, charts, text boxes, or other layout-dependent drawing content unless a
rendered-page capability is explicitly used.

Macro-enabled packages, encrypted packages, OLE objects, embedded packages, and
external relationships are rejected or surfaced as typed safety findings. No Office
application is executed during portable extraction.

Rendered DOCX mode is deferred until an isolated Word or LibreOffice boundary has
dedicated acceptance tests. Its absence must appear in coverage metadata.

## Default resource limits

Limits are configuration values, not scattered constants:

| Resource | Default |
|---|---:|
| Input file | 50 MiB |
| PDF pages | 100 |
| DOCX archive entries | 2,000 |
| DOCX total uncompressed bytes | 250 MiB |
| Single DOCX member | 50 MiB |
| Single XML member | 20 MiB |
| ZIP compression ratio | 100:1 |
| Pixels in one decoded/rendered image | 40 million |
| Total rendered pixels per document | 500 million |
| Automatically analyzed diagram candidates | 8 |
| Embedded/page perceptual duplicate comparisons | 64 |
| Tiles per diagram candidate | 24 |
| Model calls per diagram candidate | 4 |

Crossing a hard admission limit fails before any provider call. A configurable
limit may be lowered freely. Raising a limit is an explicit operator decision and
does not disable path, encryption, macro, or external-resource protections.

## Confidence semantics

All model-produced observations use these values:

- `high`: clear direct evidence with no material competing interpretation;
- `medium`: direct evidence exists but resolution, association, or semantics leave
  a plausible alternative;
- `low`: weak evidence supports a tentative interpretation that requires review;
- `unknown`: the property cannot be determined from admitted evidence.

Confidence is not a probability. Code must downgrade confidence when an endpoint,
arrowhead, label, or source region is illegible. `unknown`, `not present`, `not
visible`, and `not analyzed` remain distinct states.

## Candidate selection

Discovery records every candidate and its disposition. Without explicit selection,
the pipeline analyzes candidates classified as diagrams in document order, up to
eight. Remaining candidates are reported as skipped due to the configured limit.

Users will be able to select one page, one candidate ID, or all candidates within
the limit. `unknown` candidates remain visible but are not analyzed automatically.
Duplicate embedded-image and rendered-page representations are grouped and counted
once.

## Evidence and comparison policy

Diagram pixels and document prose are extracted independently. Captions and alt text
are document claims, not visible diagram evidence. A cross-source contradiction
requires valid evidence from both sources. The system does not decide which source
is authoritative unless the user explicitly provides that policy.

Omissions are findings only when prose claims completeness or strict-coverage mode
is selected. Non-exhaustive prose cannot prove that an extra diagram object is an
error.

## Dependency decisions

Phase A1 uses:

- the Python standard library for admission, hashing, ZIP inventory, path checks,
  bounded raster-header inspection, and OOXML package safety;
- Pydantic for strict normalized contracts;
- Poppler `pdfinfo`, `pdfdetach`, `pdftotext`, and `pdftoppm` for PDF security
  inspection, coordinate text extraction, and real page rendering;
- guarded standard-library XML parsing that rejects document type and entity
  declarations before parsing.

External Office software is optional and never a core Python dependency. Poppler is
the one required external capability for PDF ingestion and is exercised by real
integration tests. Exact Python dependencies enter `pyproject.toml` only with code
that uses them; Phase A1 adds no speculative packages.

## Controlled fixture charter

All committed fixtures must be locally generated or redistributable with recorded
provenance. Provider output never becomes reviewed ground truth automatically.

### Canonical diagram families

1. linear flow;
2. branching Yes/No flow;
3. bidirectional system architecture;
4. nested subsystem;
5. component schematic with reference numerals;
6. dense diagram requiring tiles;
7. connector crossing without a junction;
8. ambiguous low-resolution arrowhead.

### Document containers

Each relevant family receives PDF and DOCX variants covering native text, embedded
media, vector PDF rendering, table-contained images, captions, cross-references,
headers/footers, multiple images, and unsupported Word drawing coverage.

### Consistency matrix

Every supported finding category receives:

- one positive contradiction;
- one consistent negative control;
- one ambiguous or unverifiable case.

The matrix includes label, reference number, object existence, relationship,
direction, type, containment, sequence, modality, negation, alias, exhaustive scope,
and unreadable evidence.

### Safety fixtures

Fixtures cover type mismatch, truncation, malformed ZIP, traversal names, duplicate
members, encrypted members, macro content, excessive entry count, excessive member
size, total expansion, compression ratio, encrypted PDF, external relationships,
and decoded-image pixel limits.

## A0 acceptance decision

Phase A0 is complete. The product boundary, unsupported behavior, confidence model,
selection behavior, resource limits, evidence rules, dependency policy, and fixture
matrix are frozen above. The machine-readable fixture charter also records the
expected disposition of every unsupported construct and the numeric reviewer rubric,
so later phases cannot pass by omitting an adverse case or weakening a threshold.
Phase A1 may refine implementation details without silently expanding this scope.
