"""Hard evidence and normalization validation for A5 document claims."""

from __future__ import annotations

from visiogen.analysis.claims import DocumentClaimBatch, TextSelection


class ClaimValidationError(ValueError):
    """A claim response violated selected-text evidence invariants."""

    def __init__(self, findings: list[str]) -> None:
        self.findings = tuple(findings)
        super().__init__("; ".join(findings))


def normalize_claim_text(value: str) -> str:
    """Conservative normalization that never changes retained exact source text."""

    return " ".join(value.casefold().split())


def _contains_entity(evidence_text: str, entity_text: str) -> bool:
    evidence = normalize_claim_text(evidence_text)
    entity = normalize_claim_text(entity_text)
    start = evidence.find(entity)
    while start >= 0:
        end = start + len(entity)
        left_ok = start == 0 or not evidence[start - 1].isalnum()
        right_ok = end == len(evidence) or not evidence[end].isalnum()
        if left_ok and right_ok:
            return True
        start = evidence.find(entity, start + 1)
    return False


def validate_document_claims(
    batch: DocumentClaimBatch,
    selection: TextSelection,
) -> DocumentClaimBatch:
    """Reject spans outside selection, unresolved IDs, and invalid normalizations."""

    findings: list[str] = []
    if batch.candidate_id != selection.candidate_id:
        findings.append("Claim candidate_id does not match text selection")
    evidence_ids = [item.id for item in batch.evidence]
    claim_ids = [item.id for item in batch.claims]
    if len(evidence_ids) != len(set(evidence_ids)):
        findings.append("Text evidence IDs must be unique")
    if len(claim_ids) != len(set(claim_ids)):
        findings.append("Document claim IDs must be unique")
    blocks = {item.block_id: item for item in selection.blocks}
    known_evidence = set(evidence_ids)
    evidence_by_id = {item.id: item for item in batch.evidence}
    for evidence in batch.evidence:
        block = blocks.get(evidence.block_id)
        if block is None:
            findings.append(
                f"Text evidence '{evidence.id}' references unselected block '{evidence.block_id}'"
            )
            continue
        if evidence.end > len(block.text):
            findings.append(f"Text evidence '{evidence.id}' exceeds its selected block")
        elif block.text[evidence.start : evidence.end] != evidence.exact_text:
            findings.append(f"Text evidence '{evidence.id}' does not match its exact source span")
    for claim in batch.claims:
        for evidence_id in claim.evidence_ids:
            if evidence_id not in known_evidence:
                findings.append(f"Claim '{claim.id}' references unknown evidence '{evidence_id}'")
        if claim.normalized_subject != normalize_claim_text(claim.subject_text):
            findings.append(f"Claim '{claim.id}' has an invalid normalized subject")
        if claim.object_text is not None and claim.normalized_object != normalize_claim_text(
            claim.object_text
        ):
            findings.append(f"Claim '{claim.id}' has an invalid normalized object")
        cited_text = " ".join(
            evidence_by_id[evidence_id].exact_text
            for evidence_id in claim.evidence_ids
            if evidence_id in evidence_by_id
        )
        if cited_text and not _contains_entity(cited_text, claim.subject_text):
            findings.append(f"Claim '{claim.id}' subject is absent from its cited evidence")
        if (
            cited_text
            and claim.object_text is not None
            and not _contains_entity(cited_text, claim.object_text)
        ):
            findings.append(f"Claim '{claim.id}' object is absent from its cited evidence")
        if claim.predicate == "not_exists" and claim.modality != "negated":
            findings.append(f"Claim '{claim.id}' not_exists predicate requires negated modality")
        if claim.exhaustive and claim.scope in {"example", "unknown"}:
            findings.append(f"Claim '{claim.id}' has incompatible exhaustive scope")
    if findings:
        raise ClaimValidationError(findings)
    return batch


__all__ = [
    "ClaimValidationError",
    "normalize_claim_text",
    "validate_document_claims",
]
