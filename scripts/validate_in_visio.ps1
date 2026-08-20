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
        $page.Export($beforePreview)

        $moves = @()
        foreach ($label in $MoveLabels) {
            $match = Find-TopLevelShapeByLabel -Page $page -Label $label
            $root = $match.Root
            $signaturesBefore = @(Get-NativeConnectionSignatures -Page $page -RootShape $root)
            if ($signaturesBefore.Count -le 0) {
                throw "Shape '$label' has no native connection rows before movement."
            }

            $pinX = $root.CellsU("PinX")
            $pinY = $root.CellsU("PinY")
            $beforeX = [double]$pinX.ResultIU
            $beforeY = [double]$pinY.ResultIU
            $expectedX = $beforeX + 0.35
            $expectedY = $beforeY + 0.15

            # ResultIU preserves ShapeSheet formulas unless the cell is unguarded and writable.
            # A guarded or constrained cell must fail rather than being force-overwritten.
            $pinX.ResultIU = $expectedX
            $pinY.ResultIU = $expectedY
            Assert-Near -Expected $expectedX -Actual ([double]$pinX.ResultIU) -Description "Shape '$label' PinX movement"
            Assert-Near -Expected $expectedY -Actual ([double]$pinY.ResultIU) -Description "Shape '$label' PinY movement"

            $signaturesAfter = @(Get-NativeConnectionSignatures -Page $page -RootShape $root)
            Assert-SameConnectionSignatures -Label $label -Expected $signaturesBefore -Actual $signaturesAfter -Stage "after movement"

            $moves += [ordered]@{
                label = $label
                root_shape_id = [int]$root.ID
                pin_before = @($beforeX, $beforeY)
                pin_after = @([double]$pinX.ResultIU, [double]$pinY.ResultIU)
                native_connection_signatures = $signaturesBefore
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

        foreach ($move in $moves) {
            $reopenedMatch = Find-TopLevelShapeByLabel -Page $reopenedPage -Label $move.label
            $reopenedRoot = $reopenedMatch.Root
            $reopenedSignatures = @(Get-NativeConnectionSignatures -Page $reopenedPage -RootShape $reopenedRoot)
            Assert-SameConnectionSignatures -Label $move.label -Expected ([string[]]$move.native_connection_signatures) -Actual $reopenedSignatures -Stage "after save and reopen"
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
