[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputVsdx,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string[]]$MoveLabels,

    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$CoordinateTolerance = 0.0001
$ConnectorEnvelopeTolerance = 0.02

function Get-NormalizedText {
    param([AllowNull()][string]$Text)

    if ($null -eq $Text) {
        return ""
    }
    return (($Text -replace "[\r\n\t]+", " ") -replace "\s+", " ").Trim()
}

function Find-MatchingShape {
    param(
        [Parameter(Mandatory = $true)]$Shape,
        [Parameter(Mandatory = $true)][string]$NormalizedLabel
    )

    try {
        if ((Get-NormalizedText ([string]$Shape.Text)) -eq $NormalizedLabel) {
            return $Shape
        }
    }
    catch {
        # Some native shapes do not expose text through automation.
    }

    try {
        for ($index = 1; $index -le [int]$Shape.Shapes.Count; $index++) {
            $found = Find-MatchingShape -Shape $Shape.Shapes.Item($index) -NormalizedLabel $NormalizedLabel
            if ($null -ne $found) {
                return $found
            }
        }
    }
    catch {
        # A non-group shape has no child collection to search.
    }
    return $null
}

function Find-TopLevelShapeByLabel {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $normalizedLabel = Get-NormalizedText $Label
    for ($index = 1; $index -le [int]$Page.Shapes.Count; $index++) {
        $root = $Page.Shapes.Item($index)
        $matched = Find-MatchingShape -Shape $root -NormalizedLabel $normalizedLabel
        if ($null -ne $matched) {
            return [pscustomobject]@{
                Root = $root
                Matched = $matched
            }
        }
    }
    throw "Could not find requested shape label '$Label' on page one."
}

function Add-ShapeTreeIds {
    param(
        [Parameter(Mandatory = $true)]$Shape,
        [Parameter(Mandatory = $true)][hashtable]$Ids
    )

    $Ids[[int]$Shape.ID] = $true
    try {
        for ($index = 1; $index -le [int]$Shape.Shapes.Count; $index++) {
            Add-ShapeTreeIds -Shape $Shape.Shapes.Item($index) -Ids $Ids
        }
    }
    catch {
        # A non-group shape has no child collection to inspect.
    }
}

function Get-NativeConnectionSignatures {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)]$RootShape
    )

    $shapeIds = @{}
    Add-ShapeTreeIds -Shape $RootShape -Ids $shapeIds
    $signatures = New-Object System.Collections.Generic.List[string]

    for ($index = 1; $index -le [int]$Page.Connects.Count; $index++) {
        $connection = $Page.Connects.Item($index)
        $targetId = [int]$connection.ToSheet.ID
        if ($shapeIds.ContainsKey($targetId)) {
            $signature = "{0}|{1}|{2}|{3}" -f @(
                [int]$connection.FromSheet.ID,
                [string]$connection.FromCell.Name,
                $targetId,
                [string]$connection.ToCell.Name
            )
            [void]$signatures.Add($signature)
        }
    }
    return @($signatures | Sort-Object)
}

function Get-NativeEndpointCoordinates {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)]$RootShape
    )

    $shapeIds = @{}
    Add-ShapeTreeIds -Shape $RootShape -Ids $shapeIds
    $endpoints = @()
    for ($index = 1; $index -le [int]$Page.Connects.Count; $index++) {
        $connection = $Page.Connects.Item($index)
        $targetId = [int]$connection.ToSheet.ID
        if (-not $shapeIds.ContainsKey($targetId)) {
            continue
        }
        $endpointX = [string]$connection.FromCell.Name
        $endpointY = $endpointX -replace "X$", "Y"
        $connector = $connection.FromSheet
        $endpoints += [pscustomobject]@{
            key = "{0}|{1}|{2}" -f @([int]$connector.ID, $endpointX, $targetId)
            x = [double]$connector.CellsU($endpointX).ResultIU
            y = [double]$connector.CellsU($endpointY).ResultIU
        }
    }
    return @($endpoints | Sort-Object key)
}

function Assert-NativeConnectionMetadata {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    for ($index = 1; $index -le [int]$Page.Connects.Count; $index++) {
        $connection = $Page.Connects.Item($index)
        $toCellName = [string]$connection.ToCell.Name
        $actualToPart = [int]$connection.ToPart
        if ($toCellName.StartsWith("Connections.")) {
            $expectedToPart = 100 + [int]$connection.ToCell.Row
        }
        elseif ($toCellName -eq "PinX") {
            $expectedToPart = 3
        }
        else {
            throw "Unsupported native connection target '$toCellName' $Stage."
        }
        if ($actualToPart -ne $expectedToPart) {
            throw "Native connection ToPart/ToCell mismatch $Stage for connector $([int]$connection.FromSheet.ID): expected $expectedToPart for '$toCellName', got $actualToPart."
        }
    }
}

function Get-NativeConnectorsForShape {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)]$RootShape
    )

    $shapeIds = @{}
    Add-ShapeTreeIds -Shape $RootShape -Ids $shapeIds
    $seen = @{}
    $connectors = @()
    for ($index = 1; $index -le [int]$Page.Connects.Count; $index++) {
        $connection = $Page.Connects.Item($index)
        if (-not $shapeIds.ContainsKey([int]$connection.ToSheet.ID)) {
            continue
        }
        $connector = $connection.FromSheet
        $connectorId = [int]$connector.ID
        if (-not $seen.ContainsKey($connectorId)) {
            $seen[$connectorId] = $true
            $connectors += $connector
        }
    }
    return @($connectors)
}

function Assert-StraightConnectorEnvelopes {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)]$RootShape,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    foreach ($connector in @(Get-NativeConnectorsForShape -Page $Page -RootShape $RootShape)) {
        if (
            [int]$connector.CellExistsU("ShapeRouteStyle", 0) -eq 0 -or
            [int]$connector.CellExistsU("ConLineRouteExt", 0) -eq 0 -or
            [int]$connector.CellsU("ShapeRouteStyle").ResultIU -ne 2 -or
            [int]$connector.CellsU("ConLineRouteExt").ResultIU -ne 1
        ) {
            continue
        }

        $beginX = [double]$connector.CellsU("BeginX").ResultIU
        $beginY = [double]$connector.CellsU("BeginY").ResultIU
        $endX = [double]$connector.CellsU("EndX").ResultIU
        $endY = [double]$connector.CellsU("EndY").ResultIU
        $expectedLeft = [Math]::Min($beginX, $endX)
        $expectedBottom = [Math]::Min($beginY, $endY)
        $expectedRight = [Math]::Max($beginX, $endX)
        $expectedTop = [Math]::Max($beginY, $endY)
        [double]$actualLeft = 0
        [double]$actualBottom = 0
        [double]$actualRight = 0
        [double]$actualTop = 0
        $connector.BoundingBox(
            0x2004,
            [ref]$actualLeft,
            [ref]$actualBottom,
            [ref]$actualRight,
            [ref]$actualTop
        )
        foreach ($comparison in @(
            @("left", $expectedLeft, $actualLeft),
            @("bottom", $expectedBottom, $actualBottom),
            @("right", $expectedRight, $actualRight),
            @("top", $expectedTop, $actualTop)
        )) {
            if ([Math]::Abs([double]$comparison[1] - [double]$comparison[2]) -gt $ConnectorEnvelopeTolerance) {
                throw "Shape '$Label' straight connector $([int]$connector.ID) leaves its endpoint envelope $Stage at $($comparison[0]): expected $($comparison[1]), got $($comparison[2])."
            }
        }
    }
}

function Assert-EndpointOffset {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][object[]]$Before,
        [Parameter(Mandatory = $true)][object[]]$After,
        [Parameter(Mandatory = $true)][double]$DeltaX,
        [Parameter(Mandatory = $true)][double]$DeltaY,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    if ($Before.Count -ne $After.Count) {
        throw "Shape '$Label' connector endpoint count changed $Stage."
    }
    for ($index = 0; $index -lt $Before.Count; $index++) {
        if ($Before[$index].key -ne $After[$index].key) {
            throw "Shape '$Label' connector endpoint identity changed $Stage."
        }
        Assert-Near -Expected ([double]$Before[$index].x + $DeltaX) -Actual ([double]$After[$index].x) -Description "Shape '$Label' connector endpoint X $Stage"
        Assert-Near -Expected ([double]$Before[$index].y + $DeltaY) -Actual ([double]$After[$index].y) -Description "Shape '$Label' connector endpoint Y $Stage"
    }
}

function Assert-EndpointsMoved {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][object[]]$Before,
        [Parameter(Mandatory = $true)][object[]]$After
    )

    if ($Before.Count -ne $After.Count) {
        throw "Shape '$Label' connector endpoint count changed after movement."
    }
    for ($index = 0; $index -lt $Before.Count; $index++) {
        if ($Before[$index].key -ne $After[$index].key) {
            throw "Shape '$Label' connector endpoint identity changed after movement."
        }
        $deltaX = [Math]::Abs([double]$After[$index].x - [double]$Before[$index].x)
        $deltaY = [Math]::Abs([double]$After[$index].y - [double]$Before[$index].y)
        if ($deltaX -le $CoordinateTolerance -and $deltaY -le $CoordinateTolerance) {
            throw "Shape '$Label' connector endpoint stayed fixed after movement."
        }
    }
}

function Assert-SameConnectionSignatures {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string[]]$Expected,
        [Parameter(Mandatory = $true)][string[]]$Actual,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    if (($Expected -join "`n") -ne ($Actual -join "`n")) {
        throw "Shape '$Label' native connection signatures changed $Stage."
    }
}

function Assert-Near {
    param(
        [Parameter(Mandatory = $true)][double]$Expected,
        [Parameter(Mandatory = $true)][double]$Actual,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if ([Math]::Abs($Expected - $Actual) -gt $CoordinateTolerance) {
        throw "$Description did not persist: expected $Expected, got $Actual."
    }
}

function Close-VisioDocumentStrict {
    param(
        [Parameter(Mandatory = $true)]$Application,
        [Parameter(Mandatory = $true)]$Document
    )

    $fullName = [string]$Document.FullName
    $Document.Close()
    for ($index = 1; $index -le [int]$Application.Documents.Count; $index++) {
        if ([string]$Application.Documents.Item($index).FullName -eq $fullName) {
            throw "Microsoft Visio did not close the required document: $fullName"
        }
    }
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Document)
}

function Close-VisioDocumentForCleanup {
    param($Document)

    if ($null -ne $Document) {
        try { $Document.Close() } catch { }
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Document) } catch { }
    }
}

function Get-EvidenceDescriptor {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Expected evidence file was not created: $Path"
    }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Length -le 0) {
        throw "Expected evidence file is empty: $Path"
    }
    return [ordered]@{
        file = $item.Name
        size_bytes = [long]$item.Length
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$source = (Resolve-Path -LiteralPath $InputVsdx).Path
if ([System.IO.Path]::GetExtension($source).ToLowerInvariant() -ne ".vsdx") {
    throw "Input must be a .vsdx file."
}

$output = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) {
    $existing = Get-Item -LiteralPath $output -Force
    if (($existing.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing a reparse-point output directory: $output"
    }
    throw "Refusing to merge with an existing output directory: $output"
}

$parent = Split-Path -Parent $output
if ([string]::IsNullOrWhiteSpace($parent)) {
    throw "Output directory must have a parent directory."
}
[void](New-Item -ItemType Directory -Path $parent -Force)
$parentItem = Get-Item -LiteralPath $parent -Force
if (($parentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Refusing a reparse-point output parent: $parent"
}

$stagingLeaf = ".visio-acceptance-$([System.IO.Path]::GetRandomFileName())"
$stagingDirectory = Join-Path $parent $stagingLeaf
[void](New-Item -ItemType Directory -Path $stagingDirectory)

$copiedInput = Join-Path $stagingDirectory "candidate-input.vsdx"
$resavedPath = Join-Path $stagingDirectory "candidate-resaved.vsdx"
$beforePreview = Join-Path $stagingDirectory "preview-before.png"
$movedPreview = Join-Path $stagingDirectory "preview-after-move.png"
$reopenedPreview = Join-Path $stagingDirectory "preview-reopened.png"
$reportPath = Join-Path $stagingDirectory "acceptance-report.json"
Copy-Item -LiteralPath $source -Destination $copiedInput

$visio = $null
$document = $null
$reopened = $null
$published = $false

try {
    try {
        $visio = New-Object -ComObject Visio.Application
        $visio.Visible = [bool]$Visible
        $visioVersion = [string]$visio.Version

        $document = $visio.Documents.OpenEx($copiedInput, 0)
        $page = $document.Pages.Item(1)
        $initialShapeCount = [int]$page.Shapes.Count
        $initialConnectionCount = [int]$page.Connects.Count
        Assert-NativeConnectionMetadata -Page $page -Stage "after initial open"
        $page.Export($beforePreview)

        $moves = @()
        foreach ($label in $MoveLabels) {
            $match = Find-TopLevelShapeByLabel -Page $page -Label $label
            $root = $match.Root
            $signaturesBefore = @(Get-NativeConnectionSignatures -Page $page -RootShape $root)
            $endpointsBefore = @(Get-NativeEndpointCoordinates -Page $page -RootShape $root)
            if ($signaturesBefore.Count -le 0) {
                throw "Shape '$label' has no native connection rows before movement."
            }
            Assert-StraightConnectorEnvelopes -Page $page -RootShape $root -Label $label -Stage "before movement"

            $pinX = $root.CellsU("PinX")
            $pinY = $root.CellsU("PinY")
            $beforeX = [double]$pinX.ResultIU
            $beforeY = [double]$pinY.ResultIU
            $expectedX = $beforeX + 0.35
            $expectedY = $beforeY + 0.15

            $moveScope = [int]$visio.BeginUndoScope("Move Visiogen shape '$label'")
            try {
                # ResultIU preserves ShapeSheet formulas unless the cell is unguarded and writable.
                # A guarded or constrained cell must fail rather than being force-overwritten.
                $pinX.ResultIU = $expectedX
                $pinY.ResultIU = $expectedY
                $visio.EndUndoScope($moveScope, $true)
                $moveScope = 0
            }
            finally {
                if ($moveScope -ne 0) {
                    $visio.EndUndoScope($moveScope, $false)
                }
            }
            Assert-Near -Expected $expectedX -Actual ([double]$pinX.ResultIU) -Description "Shape '$label' PinX movement"
            Assert-Near -Expected $expectedY -Actual ([double]$pinY.ResultIU) -Description "Shape '$label' PinY movement"

            $signaturesAfter = @(Get-NativeConnectionSignatures -Page $page -RootShape $root)
            Assert-SameConnectionSignatures -Label $label -Expected $signaturesBefore -Actual $signaturesAfter -Stage "after movement"
            $endpointsAfter = @(Get-NativeEndpointCoordinates -Page $page -RootShape $root)
            Assert-EndpointsMoved -Label $label -Before $endpointsBefore -After $endpointsAfter
            Assert-NativeConnectionMetadata -Page $page -Stage "after moving '$label'"
            Assert-StraightConnectorEnvelopes -Page $page -RootShape $root -Label $label -Stage "after movement"

            $visio.Undo()
            Assert-Near -Expected $beforeX -Actual ([double]$pinX.ResultIU) -Description "Shape '$label' PinX after undo"
            Assert-Near -Expected $beforeY -Actual ([double]$pinY.ResultIU) -Description "Shape '$label' PinY after undo"
            $signaturesAfterUndo = @(Get-NativeConnectionSignatures -Page $page -RootShape $root)
            Assert-SameConnectionSignatures -Label $label -Expected $signaturesBefore -Actual $signaturesAfterUndo -Stage "after undo"
            $endpointsAfterUndo = @(Get-NativeEndpointCoordinates -Page $page -RootShape $root)
            Assert-EndpointOffset -Label $label -Before $endpointsBefore -After $endpointsAfterUndo -DeltaX 0 -DeltaY 0 -Stage "after undo"
            Assert-NativeConnectionMetadata -Page $page -Stage "after undoing '$label'"
            Assert-StraightConnectorEnvelopes -Page $page -RootShape $root -Label $label -Stage "after undo"

            $visio.Redo()
            Assert-Near -Expected $expectedX -Actual ([double]$pinX.ResultIU) -Description "Shape '$label' PinX after redo"
            Assert-Near -Expected $expectedY -Actual ([double]$pinY.ResultIU) -Description "Shape '$label' PinY after redo"
            $signaturesAfterRedo = @(Get-NativeConnectionSignatures -Page $page -RootShape $root)
            Assert-SameConnectionSignatures -Label $label -Expected $signaturesBefore -Actual $signaturesAfterRedo -Stage "after redo"
            $endpointsAfterRedo = @(Get-NativeEndpointCoordinates -Page $page -RootShape $root)
            Assert-EndpointOffset -Label $label -Before $endpointsAfter -After $endpointsAfterRedo -DeltaX 0 -DeltaY 0 -Stage "after redo"
            Assert-NativeConnectionMetadata -Page $page -Stage "after redoing '$label'"
            Assert-StraightConnectorEnvelopes -Page $page -RootShape $root -Label $label -Stage "after redo"

            $moves += [ordered]@{
                label = $label
                root_shape_id = [int]$root.ID
                pin_before = @($beforeX, $beforeY)
                pin_after = @([double]$pinX.ResultIU, [double]$pinY.ResultIU)
                pin_after_undo = @($beforeX, $beforeY)
                pin_after_redo = @([double]$pinX.ResultIU, [double]$pinY.ResultIU)
                native_connection_signatures = $signaturesBefore
                connector_endpoints_before = $endpointsBefore
                connector_endpoints_after = $endpointsAfterRedo
            }
        }

        $page.Export($movedPreview)
        $document.SaveAs($resavedPath)
        $savedShapeCount = [int]$page.Shapes.Count
        $savedConnectionCount = [int]$page.Connects.Count
        if ($savedShapeCount -ne $initialShapeCount) {
            throw "Top-level shape count changed during movement or save."
        }
        if ($savedConnectionCount -ne $initialConnectionCount) {
            throw "Page connection count changed during movement or save."
        }
        Close-VisioDocumentStrict -Application $visio -Document $document
        $document = $null

        $reopened = $visio.Documents.OpenEx($resavedPath, 2)
        $reopenedPage = $reopened.Pages.Item(1)
        $reopenedShapeCount = [int]$reopenedPage.Shapes.Count
        $reopenedConnectionCount = [int]$reopenedPage.Connects.Count
        if ($reopenedShapeCount -ne $savedShapeCount) {
            throw "Top-level shape count changed after save and reopen."
        }
        if ($reopenedConnectionCount -ne $savedConnectionCount) {
            throw "Page connection count changed after save and reopen."
        }
        Assert-NativeConnectionMetadata -Page $reopenedPage -Stage "after save and reopen"

        foreach ($move in $moves) {
            $reopenedMatch = Find-TopLevelShapeByLabel -Page $reopenedPage -Label $move.label
            $reopenedRoot = $reopenedMatch.Root
            $reopenedSignatures = @(Get-NativeConnectionSignatures -Page $reopenedPage -RootShape $reopenedRoot)
            Assert-SameConnectionSignatures -Label $move.label -Expected ([string[]]$move.native_connection_signatures) -Actual $reopenedSignatures -Stage "after save and reopen"
            Assert-StraightConnectorEnvelopes -Page $reopenedPage -RootShape $reopenedRoot -Label $move.label -Stage "after save and reopen"
            Assert-Near -Expected ([double]$move.pin_after[0]) -Actual ([double]$reopenedRoot.CellsU("PinX").ResultIU) -Description "Shape '$($move.label)' reopened PinX"
            Assert-Near -Expected ([double]$move.pin_after[1]) -Actual ([double]$reopenedRoot.CellsU("PinY").ResultIU) -Description "Shape '$($move.label)' reopened PinY"
            $move.reopened_pin = @(
                [double]$reopenedRoot.CellsU("PinX").ResultIU,
                [double]$reopenedRoot.CellsU("PinY").ResultIU
            )
            $move.reopened_native_connection_signatures = $reopenedSignatures
        }
        $reopenedPage.Export($reopenedPreview)
        Close-VisioDocumentStrict -Application $visio -Document $reopened
        $reopened = $null

        $visio.Quit()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($visio)
        $visio = $null

        $evidence = [ordered]@{
            input_vsdx = Get-EvidenceDescriptor -Path $copiedInput
            resaved_vsdx = Get-EvidenceDescriptor -Path $resavedPath
            preview_before = Get-EvidenceDescriptor -Path $beforePreview
            preview_after_move = Get-EvidenceDescriptor -Path $movedPreview
            preview_reopened = Get-EvidenceDescriptor -Path $reopenedPreview
        }
        $report = [ordered]@{
            status = "automation_passed"
            manual_visual_review = "pending"
            acceptance_engine = "Microsoft Visio desktop COM automation"
            generated_at_utc = [DateTime]::UtcNow.ToString("o")
            visio_version = $visioVersion
            initial_top_level_shapes = $initialShapeCount
            reopened_top_level_shapes = $reopenedShapeCount
            initial_page_connections = $initialConnectionCount
            reopened_page_connections = $reopenedConnectionCount
            moved_shapes = $moves
            evidence = $evidence
        }
        $json = $report | ConvertTo-Json -Depth 10
        [System.IO.File]::WriteAllText($reportPath, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))

        Move-Item -LiteralPath $stagingDirectory -Destination $output
        $published = $true
        Write-Output "Visio automation passed; manual visual review remains pending: $output"
    }
    finally {
        Close-VisioDocumentForCleanup $reopened
        Close-VisioDocumentForCleanup $document
        if ($null -ne $visio) {
            try { $visio.Quit() } catch { }
            try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($visio) } catch { }
        }
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }
}
catch {
    if (-not $published -and (Test-Path -LiteralPath $stagingDirectory)) {
        $failedDirectory = "$output.failed-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))"
        if (Test-Path -LiteralPath $failedDirectory) {
            $failedDirectory = "$failedDirectory-$([System.IO.Path]::GetRandomFileName())"
        }
        Move-Item -LiteralPath $stagingDirectory -Destination $failedDirectory
        Write-Warning "Native failure evidence was preserved at: $failedDirectory"
    }
    throw
}
