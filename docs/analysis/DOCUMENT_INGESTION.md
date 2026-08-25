# Deterministic Document Ingestion

**Status:** Phase A1 complete

This is the implemented boundary between untrusted PDF/DOCX inputs and later AI
analysis. It performs no model calls.

## Public library interface

```python
from visiogen.documents import extract_document

snapshot = extract_document(
    "specification.pdf",
    "artifacts/specification-ingestion",
)
```

The artifact directory must be absent or empty and must not be a symbolic link.
Extraction is staged in a private sibling directory and published atomically. A
successful bundle contains `snapshot.json` and an `assets/` directory.

## PDF behavior

PDF ingestion requires Poppler commands on `PATH`:

- `pdfinfo` for encryption, JavaScript, page count, and page geometry;
- `pdfdetach` for attachment detection;
- `pdftotext` for native text with page-relative coordinates;
- `pdftoppm` for real PNG page renders.

Every admitted page is rendered at 144 DPI. Page count, predicted pixels, actual
decoded pixels, total pixels, command runtime, and input bytes are bounded before
later analysis. Encrypted PDFs, JavaScript, attachments, malformed packages, and
missing Poppler tools fail explicitly. URLs are never followed.

PDF snapshots include:

- page count;
- native text lines and normalized bounding boxes;
- one checksum-bound PNG asset per page;
- explicit warning when no native text is extractable;
- coverage showing rendered pages complete and separate embedded-image extraction
  unavailable.

## Portable DOCX behavior

DOCX ingestion never starts Word or LibreOffice. It validates the ZIP inventory,
rejects traversal, symbolic links, duplicate/encrypted entries, macros, ActiveX,
OLE/packages, unsafe compression, unsafe XML declarations, and external
relationships.

Portable snapshots include:

- body and table paragraphs in document order;
- paragraph style names and caption classification;
- header, footer, footnote, and endnote text labeled by source part;
- drawing alt text;
- bounded PNG/JPEG/GIF media copied to checksum-bound assets;
- image dimensions without decoding untrusted pixels;
- relationship and asset references;
- explicit coverage showing that Word layout, shapes, SmartArt, charts, and text
  boxes were not rendered.

DOCX page numbers are deliberately absent in portable mode because OOXML does not
determine final pagination without a layout engine.

## Output contract

`DocumentSnapshot` validates:

- source identity and SHA-256;
- document type and media type;
- unique text and asset IDs;
- valid asset references;
- page references within the admitted page count;
- normalized positive bounding boxes;
- paired positive image dimensions;
- relative artifact paths contained within the published bundle;
- explicit modality coverage and extraction warnings.

## Remaining boundaries

Diagram discovery, image tiling, AI observation, semantic reconstruction,
description, claim extraction, and consistency checking begin in Phase A2 and later.
`visiogen analyze` is intentionally not registered yet.
