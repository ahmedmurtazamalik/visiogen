"""G2 analysis-to-generation bridge and provenance tests."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from visiogen.generation.analysis_import import (
    AnalysisImportError,
    import_analysis_bundle,
    write_specification,
)
from visiogen.generation.specification import load_specification

BUNDLES = Path("tests/fixtures/generation_v2/analysis_bundles")


def test_pdf_bundle_projects_group_and_preserves_uncertain_relationship() -> None:
    specification = import_analysis_bundle(BUNDLES / "pdf")

    assert specification.source is not None
    assert specification.source.document_kind == "pdf"
    assert specification.source.source_name == "review.pdf"
    assert specification.source.manifest_sha256
    assert [item.label for item in specification.objects] == ["Review", "Approve"]
    assert specification.relationships == []
    assert specification.groups[0].object_ids == ["object_0001", "object_0002"]
    review = {item.id: item for item in specification.review_items}
    assert review["relationship_0001_uncertainty"].evidence_refs == ["evidence-0004"]
    assert review["limitation_1"].kind == "limitation"


def test_docx_bundle_projects_semantics_references_and_evidence() -> None:
    specification = import_analysis_bundle(BUNDLES / "docx")

    assert specification.source is not None
    assert specification.source.document_kind == "docx"
    assert specification.objects[0].reference_number == "110"
    assert specification.objects[0].evidence_refs == ["evidence-0002"]
    assert specification.relationships[0].direction == "forward"
    assert specification.relationships[0].label == "samples"
    assert specification.relationships[0].evidence_refs == ["evidence-0004"]
    assert any(
        item.kind == "annotation" and "Calibrate before use" in item.description
        for item in specification.review_items
    )


def test_bundle_checksum_mismatch_fails_before_projection(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    shutil.copytree(BUNDLES / "pdf", bundle)
    diagram = bundle / "candidate-0001" / "24-analyzed-diagram.json"
    diagram.write_text(diagram.read_text() + " ")

    with pytest.raises(AnalysisImportError, match="does not match manifest checksum"):
        import_analysis_bundle(bundle)


def test_bundle_rejects_dangling_visual_evidence(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    shutil.copytree(BUNDLES / "docx", bundle)
    diagram = bundle / "candidate-0001" / "24-analyzed-diagram.json"
    value = json.loads(diagram.read_text())
    value["objects"][0]["evidence_ids"] = ["evidence-9999"]
    diagram.write_text(json.dumps(value))
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    record = next(
        item for item in manifest["artifacts"] if item["path"].endswith("24-analyzed-diagram.json")
    )
    record["sha256"] = hashlib.sha256(diagram.read_bytes()).hexdigest()
    record["byte_size"] = diagram.stat().st_size
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(AnalysisImportError, match="unknown evidence: evidence-9999"):
        import_analysis_bundle(bundle)


def test_multiple_candidates_require_explicit_selection(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    shutil.copytree(BUNDLES / "docx", bundle)
    second = bundle / "candidate-0002" / "24-analyzed-diagram.json"
    second.parent.mkdir()
    second_observations = second.parent / "14-validated-observations.json"
    observation_value = json.loads(
        (bundle / "candidate-0001" / "14-validated-observations.json").read_text()
    )
    observation_value["candidate_id"] = "candidate-0002"
    second_observations.write_text(json.dumps(observation_value))
    value = json.loads(
        (bundle / "candidate-0001" / "24-analyzed-diagram.json").read_text()
    )
    value["candidate_id"] = "candidate-0002"
    second.write_text(json.dumps(value))
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"].append(
        {
            "path": "candidate-0002/24-analyzed-diagram.json",
            "sha256": hashlib.sha256(second.read_bytes()).hexdigest(),
            "byte_size": second.stat().st_size,
        }
    )
    manifest["artifacts"].append(
        {
            "path": "candidate-0002/14-validated-observations.json",
            "sha256": hashlib.sha256(second_observations.read_bytes()).hexdigest(),
            "byte_size": second_observations.stat().st_size,
        }
    )
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(AnalysisImportError, match="--analysis-candidate"):
        import_analysis_bundle(bundle)
    selected = import_analysis_bundle(bundle, candidate_id="candidate-0002")
    assert selected.source is not None
    assert selected.source.candidate_id == "candidate-0002"


def test_reviewer_can_edit_published_draft_and_reload_it(tmp_path: Path) -> None:
    specification = import_analysis_bundle(BUNDLES / "docx")
    draft = write_specification(tmp_path / "draft.json", specification)
    value = json.loads(draft.read_text())
    value["title"] = "Reviewer-corrected sensor system"
    corrected = tmp_path / "corrected.json"
    corrected.write_text(json.dumps(value))

    reloaded = load_specification(corrected)

    assert reloaded.title == "Reviewer-corrected sensor system"
    assert reloaded.source == specification.source
    assert reloaded.relationships == specification.relationships
