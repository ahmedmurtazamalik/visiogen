# A0–A7 Completeness Audit

**Date:** 2026-08-25

**Status:** Implementation audit complete; final repository and CI gates recorded by
the audit commit and its GitHub Actions run

This audit interpreted a “silent skip” broadly: disabled or dependency-gated tests,
unrun release gates, placeholder failure types, stale status claims, unvalidated
cross-stage references, and planned evidence that could be discarded on failure.
It does not relabel the broader held-out quality, platform-specific DOCX rendering,
or arbitrary-document support planned for A8 as completed.

## Sequential findings closed

- **A0:** The fixture charter now machine-validates unsupported PDF/DOCX constructs
  and quantitative reviewer thresholds, preventing unsupported cases or release
  criteria from disappearing from prose-only documentation.
- **A1:** Poppler-backed PDF tests are mandatory rather than skipped. PDF preflight
  rejects encryption and decoded active/external action names; DOCX tests cover
  encrypted ZIP flags, symlink members, ActiveX, attachments, external actions,
  malformed/oversized images, and artifact symlink collisions.
- **A2:** Candidate selection rejects conflicting targets; tests prove limit
  dispositions and coverage, perceptual-comparison budgets, source identity,
  preparation geometry, and output-directory safety.
- **A3:** The configured model-call budget is enforced across observation and
  reconstruction. Failed calls retain traces and validation findings. Semantic
  validation now covers duplicate references, geometry/evidence intersection,
  connector support, endpoint/path grounding, exact legend/title text, and
  first-class notes/callouts with attachments and uncertainty.
- **A4:** Faithful descriptions cover annotations and exact visible tokens, including
  labels whose numerals are prefixes of other labels. Annotation coverage and
  uncertainty are scored without introducing another model call.
- **A5:** Passage selection uses token boundaries and includes diagram titles and
  connector labels while keeping diagram annotations out of independent prose
  extraction. Claims must cite spans containing their named entities. Failed repair
  calls remain auditable, and uncertain aliases cannot silently resolve later claims.
- **A6:** Alignment inputs are complete and evidence-preserving before comparison.
  Exhaustive object and relationship scopes are independent; annotation evidence is
  available to validation/adjudication; failed adjudication traces are retained.
- **A7:** Conflicting page/candidate scopes and unsafe report/evidence nesting are
  rejected. Fatal semantic/claim failures and optional adjudication failures retain
  exact call traces, validation errors, and model-call accounting in partial bundles.

## Evidence interpretation

The checksum-bound A2–A7 acceptance reports remain immutable historical evidence for
their accepted revisions. Their checksums were revalidated during this audit. New
annotation and failure-path cases are deterministic contract coverage unless a fresh
real-provider report explicitly includes them; the audit does not retroactively claim
that historical provider corpora exercised newly added cases.

The deterministic A6 corpus was rerun after the corrections and passed all 39 cases:
case agreement, confirmed-contradiction precision, evidence validity, and ambiguity
safety were 1.00, with zero non-exhaustive omission false positives.

## Remaining scope

Phase A8 still owns broader held-out documents, blinded review, measured real-world
quality, adversarial-content evaluation, platform-specific Word rendering scope, and
the final release decision. Native Microsoft Visio acceptance belongs to the separate
generation workstream and is not an A0–A7 analysis-pipeline skip.
