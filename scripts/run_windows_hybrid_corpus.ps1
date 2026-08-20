[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,

    [string]$Model = "gpt-5.6-sol",

    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

foreach ($commandName in @("git", "uv", "codex")) {
    if ($null -eq (Get-Command $commandName -ErrorAction SilentlyContinue)) {
        throw "Required command was not found on PATH: $commandName"
    }
}

$project = (Resolve-Path -LiteralPath $ProjectRoot).Path
$acceptanceScript = Join-Path $project "scripts\validate_in_visio.ps1"
if (-not (Test-Path -LiteralPath $acceptanceScript -PathType Leaf)) {
    throw "Microsoft Visio acceptance script was not found: $acceptanceScript"
}

$revision = (& git -C $project rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($revision)) {
    throw "Could not determine the source revision."
}
$worktreeStatus = (& git -C $project status --porcelain)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect the source worktree."
}
if ($worktreeStatus) {
    throw "The source worktree must be clean before running the acceptance corpus."
}

$output = [System.IO.Path]::GetFullPath($OutputDirectory)
$projectPrefix = $project.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if ($output.Equals($project, [System.StringComparison]::OrdinalIgnoreCase) -or
    $output.StartsWith($projectPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Corpus output must be outside the source checkout so provenance remains clean."
}
if (Test-Path -LiteralPath $output) {
    throw "Refusing to merge with an existing corpus directory: $output"
}
$parent = Split-Path -Parent $output
[void](New-Item -ItemType Directory -Path $parent -Force)
$parentItem = Get-Item -LiteralPath $parent -Force
if (($parentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Refusing a reparse-point corpus parent: $parent"
}

$stagingDirectory = Join-Path $parent ".hybrid-corpus-$([System.IO.Path]::GetRandomFileName())"
[void](New-Item -ItemType Directory -Path $stagingDirectory)

$cases = @(
    [ordered]@{
        Name = "flowchart"
        OutputName = "order-flow.vsdx"
        MoveLabels = @("Order Valid?", "Inventory Available?")
        Prompt = @"
Create a left-to-right order fulfillment flowchart. A customer submits an order. Validate the order. If invalid, reject it and notify the customer. If valid, check inventory. If unavailable, place the order on backorder and notify the customer. If available, authorize payment, reserve inventory, ship the order, and send delivery confirmation. Use clear decision branches and avoid crossed connectors.
"@
    },
    [ordered]@{
        Name = "system"
        OutputName = "iot-platform.vsdx"
        MoveLabels = @("Edge Gateway", "Stream Processor")
        Prompt = @"
Create a clear left-to-right architecture diagram for an IoT monitoring platform. Group field components together: multiple sensors send telemetry to an edge gateway. The gateway sends data through an ingestion API to a stream processor. The processor writes time-series data to a database and sends alerts to a notification service. A web dashboard reads from the database. Show the cloud services as one visual group, emphasize the main telemetry path, use a database shape for storage, and minimize connector crossings.
"@
    },
    [ordered]@{
        Name = "contained"
        OutputName = "smart-camera.vsdx"
        MoveLabels = @("Processor", "Radio")
        Prompt = @"
Create a contained component schematic for a smart security camera. Put Image Sensor, Processor, Memory, Radio, and Power Controller inside a Camera Housing container. The image sensor sends frames to the processor; the processor reads and writes memory; the processor sends encoded video to the radio; the power controller supplies the sensor, processor, memory, and radio. Outside the housing, show a Cloud Service connected bidirectionally to the radio. Add reference numerals to the major internal components and keep callouts readable.
"@
    }
)

$caseReports = @()
$published = $false

try {
    foreach ($case in $cases) {
        $caseDirectory = Join-Path $stagingDirectory $case.Name
        $evidenceDirectory = Join-Path $caseDirectory "generation-evidence"
        $nativeDirectory = Join-Path $caseDirectory "native-visio-acceptance"
        $promptPath = Join-Path $caseDirectory "request.txt"
        $outputVsdx = Join-Path $caseDirectory $case.OutputName
        [void](New-Item -ItemType Directory -Path $caseDirectory)
        Write-Utf8NoBom -Path $promptPath -Content ($case.Prompt.Trim() + "`n")

        $commandArguments = @(
            "run", "visiogen", "generate",
            "--input-file", $promptPath,
            "--output", $outputVsdx,
            "--artifact-dir", $evidenceDirectory,
            "--model", $Model
        )
        Push-Location $project
        try {
            & uv @commandArguments
            if ($LASTEXITCODE -ne 0) {
                throw "Hybrid generation failed for case '$($case.Name)'."
            }
        }
        finally {
            Pop-Location
        }

        $manifestPath = Join-Path $evidenceDirectory "manifest.json"
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            throw "Generation manifest is missing for case '$($case.Name)'."
        }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$manifest.source_revision -ne $revision) {
            throw "Generation source_revision mismatch for case '$($case.Name)'."
        }
        if (-not [bool]$manifest.source_worktree_clean) {
            throw "Generation did not record a clean source worktree for case '$($case.Name)'."
        }
        if (-not [bool]$manifest.visual_critique_performed) {
            throw "Visual critique was not performed for case '$($case.Name)'."
        }
        if ([string]$manifest.provider -ne "codex") {
            throw "Unexpected provider recorded for case '$($case.Name)'."
        }
        if ([string]$manifest.model -ne $Model) {
            throw "Unexpected model recorded for case '$($case.Name)'."
        }
        $generatedHash = (Get-FileHash -LiteralPath $outputVsdx -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($generatedHash -ne ([string]$manifest.output_sha256).ToLowerInvariant()) {
            throw "Generated VSDX checksum does not match its manifest for case '$($case.Name)'."
        }

        $acceptanceArguments = @{
            InputVsdx = $outputVsdx
            OutputDirectory = $nativeDirectory
            MoveLabels = [string[]]$case.MoveLabels
        }
        if ($Visible) {
            $acceptanceArguments.Visible = $true
        }
        & $acceptanceScript @acceptanceArguments

        $nativeReportPath = Join-Path $nativeDirectory "acceptance-report.json"
        $nativeReport = Get-Content -LiteralPath $nativeReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$nativeReport.status -ne "automation_passed") {
            throw "Native Microsoft Visio automation failed for case '$($case.Name)'."
        }
        $nativeSourceHash = [string]$nativeReport.evidence.input_vsdx.sha256
        if ($nativeSourceHash -ne $generatedHash) {
            throw "Native Visio input checksum does not match the generated candidate for case '$($case.Name)'."
        }

        $postNativeHash = (Get-FileHash -LiteralPath $outputVsdx -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($postNativeHash -ne $generatedHash) {
            throw "Generated VSDX changed during native acceptance for case '$($case.Name)'."
        }

        $caseReports += [ordered]@{
            name = $case.Name
            source_revision = [string]$manifest.source_revision
            provider = [string]$manifest.provider
            model = [string]$manifest.model
            visual_critique_performed = [bool]$manifest.visual_critique_performed
            revision_applied = [bool]$manifest.revision_applied
            output_sha256 = $generatedHash
            native_source_sha256 = $nativeSourceHash
            native_automation_status = [string]$nativeReport.status
            manual_visual_review = [string]$nativeReport.manual_visual_review
            resaved_sha256 = [string]$nativeReport.evidence.resaved_vsdx.sha256
            moved_shapes = @($nativeReport.moved_shapes)
        }
    }

    $closingRevision = (& git -C $project rev-parse HEAD).Trim()
    $closingStatus = (& git -C $project status --porcelain)
    if ($LASTEXITCODE -ne 0 -or $closingRevision -ne $revision -or $closingStatus) {
        throw "Source revision or worktree state changed during corpus execution."
    }

    $corpusReport = [ordered]@{
        status = "automation_passed_pending_manual_visual_review"
        generated_at_utc = [DateTime]::UtcNow.ToString("o")
        source_revision = $revision
        source_worktree_clean = $true
        provider = "codex"
        model = $Model
        visual_critique_performed = $true
        cases = $caseReports
    }
    $corpusReportPath = Join-Path $stagingDirectory "corpus-report.json"
    Write-Utf8NoBom -Path $corpusReportPath -Content (($corpusReport | ConvertTo-Json -Depth 10) + "`n")

    Move-Item -LiteralPath $stagingDirectory -Destination $output
    $published = $true
    Write-Output "Hybrid Windows automation passed; manual visual review remains pending: $output"
}
catch {
    if (-not $published -and (Test-Path -LiteralPath $stagingDirectory)) {
        $failedDirectory = "$output.failed-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))"
        if (Test-Path -LiteralPath $failedDirectory) {
            $failedDirectory = "$failedDirectory-$([System.IO.Path]::GetRandomFileName())"
        }
        Move-Item -LiteralPath $stagingDirectory -Destination $failedDirectory
        Write-Warning "Failed corpus evidence was preserved at: $failedDirectory"
    }
    throw
}
