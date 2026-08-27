# A8 Supported Scope and Known Limitations

**Release status:** Experimental pending the final held-out A8 decision

This scope applies only to diagram analysis in PDF/DOCX documents and the resulting
structured model, textual description, and consistency report. It does not cover
VSDX generation or Microsoft Visio.

## Accepted input boundary

### PDF

The intended first-release scope is ordinary, unencrypted PDF with bounded page
rendering and native text extraction when available. Full-page rendering is required
because diagrams may be vector, composite, or fragmented rather than recoverable as
one embedded image.

Encrypted files, portfolios or attachments, JavaScript, launch actions, and external
resources are rejected with typed safety errors. The pipeline does not follow links,
open attachments, execute actions, or submit passwords.

Scanned PDFs are accepted only as degraded inputs. They are not subject to clean-input
recall thresholds. Their gate is conservative uncertainty, no invented visible text,
and explicit disclosure when native document text is unavailable.

### DOCX portable mode

Portable DOCX mode supports native OOXML paragraphs, tables, headings, captions,
footnotes/endnotes where extracted, relationships, alt text, and embedded raster
media. It does not launch Microsoft Word or LibreOffice.

Portable mode does not claim visual coverage of Word shapes, SmartArt, charts, text
boxes, equations, OLE objects, or layout-dependent drawing composition. Unsupported
drawing coverage must be visible in snapshot metadata and the public report. A
portable result may still be useful when the relevant diagram is an embedded raster
image, but it must not imply complete page-level visual inspection.

### Rendered DOCX modes

`rendered_word` and `rendered_libreoffice` are reserved corpus declarations, not
accepted runtime capabilities. Either mode requires an isolated renderer boundary,
platform/tool-version provenance, deterministic page-image collection, safety tests,
and its own held-out acceptance evidence before it can be described as supported.

## Diagram and document limitations

- The supported target is technical diagrams: flowcharts, system/block diagrams,
  nested components, and schematics within the accepted corpus families.
- Photographs, general UI screenshots, tables, charts, equations, and handwritten
  whiteboards are not first-release diagram classes.
- Cross-document comparison, figure-version comparison, and multi-page logical
  diagrams are not supported.
- OCR and model readings never silently replace visible source text. Conflicts remain
  alternatives or limitations.
- The system reports evidence-grounded inconsistency; it does not decide whether the
  diagram or prose is authoritative and does not provide engineering or legal proof.
- Low resolution, occlusion, unclear arrowheads, or incomplete extraction may produce
  `unknown`, `unclear`, `unverifiable`, or partial results instead of findings.
- Provider behavior is non-deterministic. Release evidence applies only to the exact
  provider, model, source revision, corpus bytes, prompts, schemas, and bundle hashes
  recorded by the A8 decision.

## Release identity requirement

No provider/model pair is globally approved by this document. The final A8 report
must name the exact production provider and model from the complete execution report,
bind every held-out review to its bundle SHA-256, and bind deterministic hardening to
the same clean source revision. Changing the provider, model, prompts, schemas, or
analysis implementation requires a new execution and release decision.
