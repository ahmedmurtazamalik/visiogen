from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_in_visio.ps1"
CORPUS_SCRIPT = Path(__file__).parents[1] / "scripts" / "run_windows_hybrid_corpus.ps1"


def test_windows_visio_acceptance_script_exercises_native_lifecycle() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "Windows Visio validation is implemented" not in script
    assert "New-Object -ComObject Visio.Application" in script
    assert ".Documents.OpenEx(" in script
    assert ".Export(" in script
    assert ".SaveAs(" in script
    assert script.count(".Documents.OpenEx(") >= 2
    assert "Get-FileHash" in script
    assert "acceptance-report.json" in script


def test_windows_visio_acceptance_script_moves_named_shapes_and_checks_glue() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "MoveLabels" in script
    assert 'CellsU("PinX")' in script
    assert 'CellsU("PinY")' in script
    assert ".ResultIU = $expectedX" in script
    assert ".ToSheet.ID" in script
    assert ".FromSheet.ID" in script
    assert ".FromCell.Name" in script
    assert ".ToCell.Name" in script
    assert ".NameU" not in script
    assert "native connection signatures changed" in script
    assert "has no native connection rows" in script
    assert "Top-level shape count changed during movement or save" in script
    assert "Page connection count changed during movement or save" in script


def test_windows_visio_acceptance_script_stages_evidence_before_publication() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "[System.IO.Path]::GetRandomFileName()" in script
    assert "Move-Item -LiteralPath $stagingDirectory" in script
    assert "Refusing to merge with an existing output directory" in script
    assert "ReparsePoint" in script
    assert "Native failure evidence was preserved" in script
    assert 'status = "automation_passed"' in script
    assert 'manual_visual_review = "pending"' in script


def test_windows_corpus_script_runs_all_three_real_hybrid_cases() -> None:
    script = CORPUS_SCRIPT.read_text(encoding="utf-8")

    assert 'Name = "flowchart"' in script
    assert 'Name = "system"' in script
    assert 'Name = "contained"' in script
    assert '"visiogen", "generate"' in script
    assert "--no-critique" not in script
    assert "validate_in_visio.ps1" in script
    assert "corpus-report.json" in script


def test_windows_corpus_script_preserves_failed_evidence_and_refuses_merges() -> None:
    script = CORPUS_SCRIPT.read_text(encoding="utf-8")

    assert "Refusing to merge with an existing corpus directory" in script
    assert "failed-" in script
    assert "source_revision" in script
    assert "visual_critique_performed" in script
    assert "revision_applied" in script
    assert "revision_performed" not in script
    assert "nativeSourceHash -ne $generatedHash" in script
    assert "automation_passed_pending_manual_visual_review" in script
