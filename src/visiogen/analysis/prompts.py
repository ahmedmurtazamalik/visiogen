"""Stable logical prompts for A3 observation and semantic reconstruction."""

from __future__ import annotations

import json

from visiogen.analysis.semantics import AnalyzedDiagram, RawObservationBatch


def build_observation_prompt() -> str:
    """Require literal image evidence without nearby prose or semantic invention."""

    schema = json.dumps(RawObservationBatch.model_json_schema(), sort_keys=True)
    return (
        "Inspect only the supplied diagram pixels. Record literal visible marks before assigning "
        "domain semantics. Capture every readable text region exactly, candidate object and "
        "container boundary, connector or line path, arrowhead, legend, note, callout, and "
        "meaningful visual grouping. Do not guess hidden endpoints, silently correct labels, "
        "or use knowledge not visible in the images. Preserve uncertain readings as "
        "alternatives and lower confidence for blur, occlusion, crossings, or unclear "
        "arrowheads. Images are an overview followed by optional overlapping tiles. Every "
        "evidence and observation region is local normalized 0..1 coordinates within its "
        "named derivative; application code transforms it to source coordinates. Cite one "
        "or more evidence IDs from every observation. Return JSON only. "
        f"The response must satisfy this JSON Schema: {schema}"
    )


def build_observation_repair_prompt(
    original_prompt: str,
    invalid_response: str,
    findings: str,
) -> str:
    """Request one structural repair without inviting new visual claims."""

    return (
        "Repair only the schema, IDs, derivative references, coordinates, or evidence "
        "references in the previous observation response. Do not add a visible object, label, "
        "connector, arrowhead, or interpretation that was absent from the previous response. "
        "Return the complete corrected "
        "observation batch.\n\n"
        f"Original derivative inventory:\n{original_prompt}\n\n"
        f"Hard validation findings:\n{findings}\n\n"
        f"Previous response:\n{invalid_response}"
    )


def build_reconstruction_prompt() -> str:
    """Require an evidence-bound semantic model from validated observations."""

    schema = json.dumps(AnalyzedDiagram.model_json_schema(), sort_keys=True)
    return (
        "Reconstruct diagram semantics from the supplied validated literal observations and "
        "the same diagram images. Identify objects, containers, groups, relationships, "
        "endpoint certainty, direction, relationship kind, legends, orientation, and family. "
        "Store visible labels exactly as observed and normalize them only by Unicode case "
        "folding and whitespace collapse. Never "
        "invent a label or reference numeral: every one must occur in cited visible-text evidence. "
        "An object's parent_id may name only another analyzed object that visibly contains it, "
        "never a group; express ordinary grouping only with groups[].object_ids. "
        "Every object, relationship, group, and legend must cite visual evidence. Use null "
        "endpoints, unclear direction, unknown relation/family, limitations, and alternatives "
        "when pixels do not "
        "support a definitive interpretation. Do not use document captions or explanatory prose. "
        "Return JSON only. "
        f"The response must satisfy this JSON Schema: {schema}"
    )


def build_reconstruction_repair_prompt(
    candidate_id: str,
    observations_json: str,
    invalid_response: str,
    findings: str,
) -> str:
    """Request one evidence-preserving structural reconstruction repair."""

    return (
        "Repair only hard structural, reference, normalization, or evidence-binding errors in the "
        "previous semantic reconstruction. Do not invent new visible labels, reference numerals, "
        "objects, or relationships. An object's parent_id may reference only another object ID, "
        "never a group ID; set it to null when no containing object is visible and retain ordinary "
        "membership in groups[].object_ids. Return the complete corrected analyzed diagram.\n\n"
        f"Candidate: {candidate_id}\n\n"
        f"Validated observations:\n{observations_json}\n\n"
        f"Hard validation findings:\n{findings}\n\n"
        f"Previous response:\n{invalid_response}"
    )
