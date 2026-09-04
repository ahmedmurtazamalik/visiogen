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
    assert '.BeginUndoScope("Move Visiogen shape' in script
    assert "$visio.Undo()" in script
    assert "$visio.Redo()" in script
    assert "PinX after undo" in script
    assert "PinY after redo" in script
    assert "after undo" in script
    assert "after redo" in script
    assert "Get-NativeEndpointCoordinates" in script
    assert "Assert-EndpointOffset" in script
    assert "Assert-EndpointsMoved" in script
    assert "Assert-NativeConnectionMetadata" in script
    assert "Assert-NativeRoutingPolicy" in script
    assert "Assert-ShapeDrawingWithinTransform" in script
    assert "Assert-StaticEndpointsMatchConnectionPoints" in script
    assert "Assert-StraightConnectorEnvelopes" in script
    assert "unsupported routing policy" in script
    assert "drawing leaves its Width/Height transform" in script
    assert "static connector endpoint X" in script
    assert "static connector endpoint Y" in script
    assert "has no ConFixedCode cell" in script
    assert "has no ShapeRouteStyle cell" in script
    assert ".XYToPage(" in script
    assert 'CellsU("BeginArrow")' in script
    assert 'CellsU("EndArrow")' in script
    assert ".ToPart" in script
    assert ".ToCell.Row" in script
    assert ".BoundingBox(" in script
    assert "leaves its endpoint envelope" in script
    assert "connector endpoint stayed fixed after movement" in script
    assert "connector endpoint X" in script
    assert "connector endpoint Y" in script
    assert ".ToSheet.ID" in script
    assert ".FromSheet.ID" in script
    assert ".FromCell.Name" in script
    assert ".ToCell.Name" in script
    assert ".FromCell.NameU" not in script
    assert ".ToCell.NameU" not in script
    assert "native connection signatures changed" in script
    assert "has no native connection rows" in script
    assert "Top-level shape count changed during movement or save" in script
    assert "Page connection count changed during movement or save" in script


def test_windows_visio_acceptance_script_checks_orthogonal_terminal_legs() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "Get-ConnectorRoutePoints" in script
    assert "Get-OrthogonalTerminalLeg" in script
    assert "Get-ConnectionDirectionOnPage" in script
    assert "Assert-OrthogonalTerminalLegs" in script
    assert script.count("Assert-OrthogonalTerminalLegs -Page") >= 5
    assert ".GeometryCount" in script
    assert ".RowCount(" in script
    assert "for ($row = 1; $row -lt $rowCount; $row++)" in script
    assert "Row zero is the Geometry section-properties row" in script
    assert ".RowExists(" in script
    assert ".RowType(" in script
    assert ".RowsCellCount(" in script
    assert ".GetPolylineData(0x20" in script
    assert "versions that already include the last point" in script
    assert "$points += $polylineEnd" in script
    assert "CellsSRC($section, $row, 0)" in script
    assert "CellsSRC(7, $row, 2)" in script
    assert "CellsSRC(7, $row, 3)" in script
    assert "zero-length terminal leg" in script
    assert "non-orthogonal terminal leg" in script
    assert "does not exit opposite its inward port direction" in script
    assert 'CellsU("ShapeRouteStyle").ResultIU -ne 1' in script
    assert "freeform/polyline connectors have separate contracts" in script


def test_windows_visio_acceptance_script_crosses_a_safe_terminal_bend() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "Get-PreferredMoveDelta" in script
    assert "Test-TranslatedShapeWithinPage" in script
    assert 'Strategy = "cross_terminal_bend"' in script
    assert "The endpoint-adjacent vertex must be a real orthogonal corner" in script
    assert "$expectedX = $beforeX + [double]$moveDelta.DeltaX" in script
    assert "$expectedY = $beforeY + [double]$moveDelta.DeltaY" in script
    assert "movement_delta" in script
    assert "movement_strategy" in script
    assert "bend_before_crossing" in script
    assert "RequireBendCrossing" in script
    assert "No requested shape could be moved safely across" in script
    assert "terminal_bend_crossed" in script


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
    assert "RequireBendCrossing = $true" in script
    assert "nativeReport.terminal_bend_crossed" in script
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
