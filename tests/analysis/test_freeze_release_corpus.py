"""A8 draft-to-immutable-corpus tests."""

import hashlib
import json
from pathlib import Path
import runpy

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "freeze_analysis_release_corpus.py"
freeze_corpus = runpy.run_path(str(SCRIPT), run_name="freeze_contract")["freeze_corpus"]
TAGS = [
    "clean_native_text_pdf", "system_architecture_docx", "dense_reference_schematic",
    "vector_pdf", "low_quality_scan", "mixed_diagram_and_non_diagram", "prompt_injection",
]


def _write_draft(root: Path) -> Path:
    sources = root / "sources"
    sources.mkdir(parents=True)
    cases = []
    for index, tag in enumerate(TAGS):
        is_docx = tag in {"system_architecture_docx", "mixed_diagram_and_non_diagram"}
        suffix = "docx" if is_docx else "pdf"
        relative = f"sources/case-{index}.{suffix}"
        (root / relative).write_bytes(f"source-{index}".encode())
        case = {"id": f"case-{index}", "subset": "held_out", "document_kind": suffix,
                "source_path": relative, "clean_input": tag != "low_quality_scan",
                "coverage_tags": [tag]}
        if is_docx:
            case["docx_mode"] = "portable"
        if tag == "prompt_injection":
            case["adversarial_prompt_injection"] = True
        cases.append(case)
    draft = root / "draft.json"
    draft.write_text(json.dumps({"version": 1, "thresholds": {}, "cases": cases}))
    return draft


def test_freeze_corpus_hashes_exact_sources_and_preserves_declared_split(tmp_path) -> None:
    frozen = freeze_corpus(_write_draft(tmp_path))
    assert len(frozen["cases"]) == 7
    assert frozen["cases"][0]["source_sha256"] == hashlib.sha256(b"source-0").hexdigest()
    assert frozen["cases"][0]["subset"] == "held_out"


def test_freeze_corpus_rejects_unsafe_or_prefilled_sources(tmp_path) -> None:
    draft = _write_draft(tmp_path / "first")
    raw = json.loads(draft.read_text())
    raw["cases"][0]["source_path"] = "../escape.pdf"
    draft.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="relative POSIX paths"):
        freeze_corpus(draft)

    draft = _write_draft(tmp_path / "second")
    raw = json.loads(draft.read_text())
    raw["cases"][0]["source_sha256"] = "a" * 64
    draft.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="must not contain source_sha256"):
        freeze_corpus(draft)


def test_example_draft_declares_every_required_held_out_family() -> None:
    example = SCRIPT.parents[1] / "docs" / "analysis" / "A8_CORPUS_DRAFT.example.json"
    raw = json.loads(example.read_text())
    tags = {tag for case in raw["cases"] for tag in case["coverage_tags"]}
    assert tags == set(TAGS)
    assert all(case["subset"] == "held_out" for case in raw["cases"])
    assert all("source_sha256" not in case for case in raw["cases"])
