# A8 Deterministic Hardening Acceptance

**Status:** Passed

**Source revision:** `2b1f363a621fe3e62a71fad99c8f40e19fa393cb`

**Executed:** 2026-08-27T03:49:27Z

The A8 deterministic security and resource-limit gate ran from a clean checkout and
passed all 32 selected tests. The gate is analysis-only and covers PDF/DOCX input
admission, not VSDX generation.

## Covered boundaries

- PDF JavaScript, launch, external, encrypted, malformed, and obfuscated actions;
- DOCX traversal, duplicate/encrypted/symlink members, macro/ActiveX content, and
  entry/member/total-expansion/compression limits;
- input-file, decoded-image, rendered/tiled image, and candidate preparation limits;
- prompt-injection text kept as quoted data and source-controlled Markdown escaping;
- atomic artifact publication, unsafe output rejection, partial-result retention,
  failed-call trace preservation, manifest tampering detection, and VSDX exclusion.

## Preserved evidence

The exact machine report is
[`evidence/a8-hardening.json`](evidence/a8-hardening.json). It binds every selected
test file to a SHA-256 digest. The external run additionally preserved JUnit and
captured stdout:

- acceptance report SHA-256:
  `5a8c7dcc1ae07a5f8d9c91abad48ecb2fd81c05b5b5216947345c1b450e82d59`;
- JUnit SHA-256:
  `b1d64039c21d3e2f655ae4f3e3f224575797a95af53bcad4467823c4dd32a28b`;
- stdout SHA-256:
  `660e346bbda72bdfb2bf4b35d52340eb0ff010d02288e5e6c6c7afc127fed561`.

This closes the deterministic A8 hardening sub-gate. It does not replace the real
provider corpus, blinded human review, held-out quality scoring, or final release
decision.
