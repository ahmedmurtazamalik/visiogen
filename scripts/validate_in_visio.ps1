[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputVsdx,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string[]]$MoveLabels,

    [switch]$RequireBendCrossing,

    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$CoordinateTolerance = 0.0001
$ConnectorEnvelopeTolerance = 0.02
$ShapeEnvelopeTolerance = 0.05

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
            $signature += "|{0}|{1}" -f @(
                [int]$connection.FromSheet.CellsU("BeginArrow").ResultIU,
                [int]$connection.FromSheet.CellsU("EndArrow").ResultIU
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

function Assert-NativeRoutingPolicy {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    $seen = @{}
    for ($index = 1; $index -le [int]$Page.Connects.Count; $index++) {
        $connector = $Page.Connects.Item($index).FromSheet
        $connectorId = [int]$connector.ID
        if ($seen.ContainsKey($connectorId)) {
            continue
        }
        $seen[$connectorId] = $true
        if ([int]$connector.CellExistsU("ConFixedCode", 0) -eq 0) {
            throw "Connector $connectorId has no ConFixedCode cell $Stage."
        }
        $fixedCode = [int]$connector.CellsU("ConFixedCode").ResultIU
        if ([int]$connector.CellExistsU("ShapeRouteStyle", 0) -eq 0) {
            throw "Connector $connectorId has no ShapeRouteStyle cell $Stage."
        }
        $routeStyle = [int]$connector.CellsU("ShapeRouteStyle").ResultIU
        $routeExtension = 0
        if ([int]$connector.CellExistsU("ConLineRouteExt", 0) -ne 0) {
            $routeExtension = [int]$connector.CellsU("ConLineRouteExt").ResultIU
        }
        $isFixedPolyline = (
            $fixedCode -eq 2 -and
            $routeStyle -eq 2 -and
            $routeExtension -eq 0
        )
        if ($fixedCode -ne 0 -and -not $isFixedPolyline) {
            throw "Connector $connectorId has unsupported routing policy $Stage (ConFixedCode=$fixedCode, ShapeRouteStyle=$routeStyle, ConLineRouteExt=$routeExtension)."
        }
    }
}

function Get-ShapeDrawingBounds {
    param([Parameter(Mandatory = $true)]$Shape)

    [double]$left = 0
    [double]$bottom = 0
    [double]$right = 0
    [double]$top = 0
    $Shape.BoundingBox(
        0x2004,
        [ref]$left,
        [ref]$bottom,
        [ref]$right,
        [ref]$top
    )
    return [pscustomobject]@{
        left = $left
        bottom = $bottom
        right = $right
        top = $top
    }
}

function Assert-ShapeDrawingWithinTransform {
    param(
        [Parameter(Mandatory = $true)]$RootShape,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    try {
        $masterName = [string]$RootShape.Master.NameU
    }
    catch {
        return
    }
    $boundedMasters = @(
        "Process",
        "Rectangle",
        "Start/End",
        "Decision",
        "Subprocess",
        "Delay",
        "On-page reference",
        "Rounded Rectangle",
        "Circle",
        "Plain",
        "Classic"
    )
    if ($masterName -notin $boundedMasters) {
        return
    }

    $pinX = [double]$RootShape.CellsU("PinX").ResultIU
    $pinY = [double]$RootShape.CellsU("PinY").ResultIU
    $locPinX = [double]$RootShape.CellsU("LocPinX").ResultIU
    $locPinY = [double]$RootShape.CellsU("LocPinY").ResultIU
    $width = [double]$RootShape.CellsU("Width").ResultIU
    $height = [double]$RootShape.CellsU("Height").ResultIU
    $expectedLeft = $pinX - $locPinX
    $expectedBottom = $pinY - $locPinY
    $expectedRight = $expectedLeft + $width
    $expectedTop = $expectedBottom + $height
    $actual = Get-ShapeDrawingBounds -Shape $RootShape
    if (
        $actual.left -lt $expectedLeft - $ShapeEnvelopeTolerance -or
        $actual.bottom -lt $expectedBottom - $ShapeEnvelopeTolerance -or
        $actual.right -gt $expectedRight + $ShapeEnvelopeTolerance -or
        $actual.top -gt $expectedTop + $ShapeEnvelopeTolerance
    ) {
        throw "Shape '$Label' drawing leaves its Width/Height transform $Stage. Expected [$expectedLeft,$expectedBottom,$expectedRight,$expectedTop], got [$($actual.left),$($actual.bottom),$($actual.right),$($actual.top)]."
    }
}

function Assert-StaticEndpointsMatchConnectionPoints {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)]$RootShape,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    $shapeIds = @{}
    Add-ShapeTreeIds -Shape $RootShape -Ids $shapeIds
    for ($index = 1; $index -le [int]$Page.Connects.Count; $index++) {
        $connection = $Page.Connects.Item($index)
        $target = $connection.ToSheet
        if (-not $shapeIds.ContainsKey([int]$target.ID)) {
            continue
        }
        $toCellName = [string]$connection.ToCell.Name
        if (-not $toCellName.StartsWith("Connections.")) {
            continue
        }
        $row = [int]$connection.ToCell.Row
        $localX = [double]$target.CellsSRC(7, $row, 0).ResultIU
        $localY = [double]$target.CellsSRC(7, $row, 1).ResultIU
        [double]$expectedX = 0
        [double]$expectedY = 0
        $target.XYToPage($localX, $localY, [ref]$expectedX, [ref]$expectedY)

        $endpointX = [string]$connection.FromCell.Name
        $endpointY = $endpointX -replace "X$", "Y"
        $connector = $connection.FromSheet
        Assert-Near -Expected $expectedX -Actual ([double]$connector.CellsU($endpointX).ResultIU) -Description "Shape '$Label' static connector endpoint X $Stage"
        Assert-Near -Expected $expectedY -Actual ([double]$connector.CellsU($endpointY).ResultIU) -Description "Shape '$Label' static connector endpoint Y $Stage"
        if ($endpointY -eq $endpointX) {
            throw "Unsupported connector endpoint cell '$endpointX' $Stage."
        }
    }
}

function Convert-ShapePointToPage {
    param(
        [Parameter(Mandatory = $true)]$Shape,
        [Parameter(Mandatory = $true)][double]$X,
        [Parameter(Mandatory = $true)][double]$Y
    )

    [double]$pageX = 0
    [double]$pageY = 0
    [void]$Shape.XYToPage($X, $Y, [ref]$pageX, [ref]$pageY)
    return [pscustomobject]@{
        x = $pageX
        y = $pageY
    }
}

function Test-PointsNear {
    param(
        [Parameter(Mandatory = $true)]$First,
        [Parameter(Mandatory = $true)]$Second
    )

    return (
        [Math]::Abs([double]$First.x - [double]$Second.x) -le $ConnectorEnvelopeTolerance -and
        [Math]::Abs([double]$First.y - [double]$Second.y) -le $ConnectorEnvelopeTolerance
    )
}

function Get-ConnectorRoutePoints {
    param(
        [Parameter(Mandatory = $true)]$Connector,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    $begin = [pscustomobject]@{
        x = [double]$Connector.CellsU("BeginX").ResultIU
        y = [double]$Connector.CellsU("BeginY").ResultIU
    }
    $end = [pscustomobject]@{
        x = [double]$Connector.CellsU("EndX").ResultIU
        y = [double]$Connector.CellsU("EndY").ResultIU
    }
    $geometryCount = [int]$Connector.GeometryCount
    for ($geometryIndex = 0; $geometryIndex -lt $geometryCount; $geometryIndex++) {
        # visSectionFirstComponent is 10; subsequent Geometry sections are contiguous.
        $section = 10 + $geometryIndex
        $rowCount = [int]$Connector.RowCount($section)
        if ($rowCount -lt 2) {
            continue
        }

        $points = @()
        $unsupportedGeometry = $false
        # visRowVertex is one. Row zero is the Geometry section-properties row
        # (NoFill/NoLine/etc.), not a route vertex.
        for ($row = 1; $row -lt $rowCount; $row++) {
            if ([int]$Connector.RowExists($section, $row, 0) -eq 0) {
                continue
            }
            $rowType = [int]$Connector.RowType($section, $row)
            if ([int]$Connector.RowsCellCount($section, $row) -lt 2) {
                continue
            }

            if ($rowType -eq 193) {
                # Native routing can compact LineTo rows into one PolylineTo row.
                # visGeomXYLocal (0x20) returns every stored vertex in shape-local IU.
                $xyValues = $null
                $geometryRow = $Connector.Section($section).Row($row)
                [void]$geometryRow.GetPolylineData(0x20, [ref]$xyValues)
                $coordinates = @($xyValues)
                if (($coordinates.Count % 2) -ne 0) {
                    throw "Connector $([int]$Connector.ID) has malformed PolylineTo Geometry data $Stage."
                }
                for ($coordinateIndex = 0; $coordinateIndex -lt $coordinates.Count; $coordinateIndex += 2) {
                    $points += Convert-ShapePointToPage `
                        -Shape $Connector `
                        -X ([double]$coordinates[$coordinateIndex]) `
                        -Y ([double]$coordinates[$coordinateIndex + 1])
                }
                # GetPolylineData expands the A-cell vertices. Append the row's
                # explicit X/Y endpoint as well, without duplicating it on COM
                # versions that already include the last point.
                $polylineEnd = Convert-ShapePointToPage `
                    -Shape $Connector `
                    -X ([double]$Connector.CellsSRC($section, $row, 0).ResultIU) `
                    -Y ([double]$Connector.CellsSRC($section, $row, 1).ResultIU)
                $lastPoint = if ($points.Count -gt 0) { $points[$points.Count - 1] } else { $null }
                if (
                    $null -eq $lastPoint -or
                    [Math]::Abs([double]$lastPoint.x - [double]$polylineEnd.x) -gt $CoordinateTolerance -or
                    [Math]::Abs([double]$lastPoint.y - [double]$polylineEnd.y) -gt $CoordinateTolerance
                ) {
                    $points += $polylineEnd
                }
                continue
            }
            if ($rowType -ne 138 -and $rowType -ne 139) {
                # Curved/spline rows cannot satisfy an orthogonal route contract.
                $unsupportedGeometry = $true
                break
            }
            $localX = [double]$Connector.CellsSRC($section, $row, 0).ResultIU
            $localY = [double]$Connector.CellsSRC($section, $row, 1).ResultIU
            $points += Convert-ShapePointToPage -Shape $Connector -X $localX -Y $localY
        }
        if ($unsupportedGeometry -or $points.Count -lt 2) {
            continue
        }

        $first = $points[0]
        $last = $points[$points.Count - 1]
        if ((Test-PointsNear -First $first -Second $begin) -and
            (Test-PointsNear -First $last -Second $end)) {
            return @($points)
        }
        if ((Test-PointsNear -First $first -Second $end) -and
            (Test-PointsNear -First $last -Second $begin)) {
            $reversed = @()
            for ($pointIndex = $points.Count - 1; $pointIndex -ge 0; $pointIndex--) {
                $reversed += $points[$pointIndex]
            }
            return @($reversed)
        }
    }
    throw "Connector $([int]$Connector.ID) has no active Geometry path matching its endpoints $Stage."
}

function Get-OrthogonalTerminalLeg {
    param(
        [Parameter(Mandatory = $true)]$Connector,
        [Parameter(Mandatory = $true)][string]$EndpointX,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    $points = @(Get-ConnectorRoutePoints -Connector $Connector -Stage $Stage)
    if ($EndpointX -eq "BeginX") {
        $endpoint = $points[0]
        $adjacent = $points[1]
        $beyondAdjacent = if ($points.Count -ge 3) { $points[2] } else { $null }
    }
    elseif ($EndpointX -eq "EndX") {
        $endpoint = $points[$points.Count - 1]
        $adjacent = $points[$points.Count - 2]
        $beyondAdjacent = if ($points.Count -ge 3) { $points[$points.Count - 3] } else { $null }
    }
    else {
        throw "Unsupported orthogonal connector endpoint '$EndpointX' $Stage."
    }
    return [pscustomobject]@{
        Endpoint = $endpoint
        Adjacent = $adjacent
        DeltaX = [double]$adjacent.x - [double]$endpoint.x
        DeltaY = [double]$adjacent.y - [double]$endpoint.y
        BeyondAdjacent = $beyondAdjacent
        PointCount = $points.Count
    }
}

function Get-ConnectionDirectionOnPage {
    param([Parameter(Mandatory = $true)]$Connection)

    $target = $Connection.ToSheet
    $row = [int]$Connection.ToCell.Row
    # visSectionConnectionPts=7, visCnnctDirX=2, visCnnctDirY=3.
    $localDirX = [double]$target.CellsSRC(7, $row, 2).ResultIU
    $localDirY = [double]$target.CellsSRC(7, $row, 3).ResultIU
    $origin = Convert-ShapePointToPage -Shape $target -X 0 -Y 0
    $tip = Convert-ShapePointToPage -Shape $target -X $localDirX -Y $localDirY
    return [pscustomobject]@{
        x = [double]$tip.x - [double]$origin.x
        y = [double]$tip.y - [double]$origin.y
    }
}

function Assert-OrthogonalTerminalLegs {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    for ($index = 1; $index -le [int]$Page.Connects.Count; $index++) {
        $connection = $Page.Connects.Item($index)
        $connector = $connection.FromSheet
        if (
            [int]$connector.CellExistsU("ShapeRouteStyle", 0) -eq 0 -or
            [int]$connector.CellsU("ShapeRouteStyle").ResultIU -ne 1
        ) {
            # Straight, dynamic, and freeform/polyline connectors have separate contracts.
            continue
        }
        $toCellName = [string]$connection.ToCell.Name
        if (-not $toCellName.StartsWith("Connections.")) {
            throw "Orthogonal connector $([int]$connector.ID) is not statically glued $Stage."
        }

        $endpointX = [string]$connection.FromCell.Name
        $leg = Get-OrthogonalTerminalLeg -Connector $connector -EndpointX $endpointX -Stage $Stage
        $legLength = [Math]::Sqrt($leg.DeltaX * $leg.DeltaX + $leg.DeltaY * $leg.DeltaY)
        if ($legLength -le $CoordinateTolerance) {
            throw "Orthogonal connector $([int]$connector.ID) has a zero-length terminal leg at '$endpointX' $Stage."
        }
        if (
            [Math]::Abs([double]$leg.DeltaX) -gt $ConnectorEnvelopeTolerance -and
            [Math]::Abs([double]$leg.DeltaY) -gt $ConnectorEnvelopeTolerance
        ) {
            throw "Orthogonal connector $([int]$connector.ID) has a non-orthogonal terminal leg at '$endpointX' $Stage."
        }

        $direction = Get-ConnectionDirectionOnPage -Connection $connection
        $directionLength = [Math]::Sqrt(
            $direction.x * $direction.x + $direction.y * $direction.y
        )
        if ($directionLength -le $CoordinateTolerance) {
            throw "Orthogonal connector $([int]$connector.ID) has no inward port direction at '$endpointX' $Stage."
        }
        $alignment = (
            $leg.DeltaX * $direction.x + $leg.DeltaY * $direction.y
        ) / ($legLength * $directionLength)
        if ($alignment -ge -0.9) {
            throw "Orthogonal connector $([int]$connector.ID) terminal leg at '$endpointX' does not exit opposite its inward port direction $Stage."
        }
    }
}

function Test-TranslatedShapeWithinPage {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)]$RootShape,
        [Parameter(Mandatory = $true)][double]$DeltaX,
        [Parameter(Mandatory = $true)][double]$DeltaY
    )

    $bounds = Get-ShapeDrawingBounds -Shape $RootShape
    $pageWidth = [double]$Page.PageSheet.CellsU("PageWidth").ResultIU
    $pageHeight = [double]$Page.PageSheet.CellsU("PageHeight").ResultIU
    $inset = 0.05
    return (
        $bounds.left + $DeltaX -ge $inset -and
        $bounds.bottom + $DeltaY -ge $inset -and
        $bounds.right + $DeltaX -le $pageWidth - $inset -and
        $bounds.top + $DeltaY -le $pageHeight - $inset
    )
}

function Get-PreferredMoveDelta {
    param(
        [Parameter(Mandatory = $true)]$Page,
        [Parameter(Mandatory = $true)]$RootShape,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    $shapeIds = @{}
    Add-ShapeTreeIds -Shape $RootShape -Ids $shapeIds
    $candidates = @()
    for ($index = 1; $index -le [int]$Page.Connects.Count; $index++) {
        $connection = $Page.Connects.Item($index)
        if (-not $shapeIds.ContainsKey([int]$connection.ToSheet.ID)) {
            continue
        }
        $connector = $connection.FromSheet
        if (
            [int]$connector.CellExistsU("ShapeRouteStyle", 0) -eq 0 -or
            [int]$connector.CellsU("ShapeRouteStyle").ResultIU -ne 1 -or
            -not ([string]$connection.ToCell.Name).StartsWith("Connections.")
        ) {
            continue
        }

        $endpointX = [string]$connection.FromCell.Name
        $leg = Get-OrthogonalTerminalLeg -Connector $connector -EndpointX $endpointX -Stage $Stage
        if ($leg.PointCount -lt 3 -or $null -eq $leg.BeyondAdjacent) {
            # With two points the adjacent point is the opposite endpoint, not a bend.
            continue
        }
        $nextDeltaX = [double]$leg.BeyondAdjacent.x - [double]$leg.Adjacent.x
        $nextDeltaY = [double]$leg.BeyondAdjacent.y - [double]$leg.Adjacent.y
        $terminalIsHorizontal = (
            [Math]::Abs([double]$leg.DeltaX) -gt $CoordinateTolerance -and
            [Math]::Abs([double]$leg.DeltaY) -le $ConnectorEnvelopeTolerance
        )
        $terminalIsVertical = (
            [Math]::Abs([double]$leg.DeltaY) -gt $CoordinateTolerance -and
            [Math]::Abs([double]$leg.DeltaX) -le $ConnectorEnvelopeTolerance
        )
        $nextIsHorizontal = (
            [Math]::Abs($nextDeltaX) -gt $CoordinateTolerance -and
            [Math]::Abs($nextDeltaY) -le $ConnectorEnvelopeTolerance
        )
        $nextIsVertical = (
            [Math]::Abs($nextDeltaY) -gt $CoordinateTolerance -and
            [Math]::Abs($nextDeltaX) -le $ConnectorEnvelopeTolerance
        )
        if (-not (
            ($terminalIsHorizontal -and $nextIsVertical) -or
            ($terminalIsVertical -and $nextIsHorizontal)
        )) {
            # The endpoint-adjacent vertex must be a real orthogonal corner.
            continue
        }
        $deltaX = 0.0
        $deltaY = 0.0
        $overshoot = 0.2
        if ($terminalIsHorizontal) {
            $deltaX = [double]$leg.DeltaX + [Math]::Sign([double]$leg.DeltaX) * $overshoot
        }
        elseif ($terminalIsVertical) {
            $deltaY = [double]$leg.DeltaY + [Math]::Sign([double]$leg.DeltaY) * $overshoot
        }
        else {
            continue
        }
        $magnitude = [Math]::Sqrt($deltaX * $deltaX + $deltaY * $deltaY)
        if (-not (
            Test-TranslatedShapeWithinPage -Page $Page -RootShape $RootShape -DeltaX $deltaX -DeltaY $deltaY
        )) {
            continue
        }
        $candidates += [pscustomobject]@{
            DeltaX = $deltaX
            DeltaY = $deltaY
            Strategy = "cross_terminal_bend"
            ConnectorId = [int]$connector.ID
            EndpointX = $endpointX
            EndpointBefore = @([double]$leg.Endpoint.x, [double]$leg.Endpoint.y)
            BendBefore = @([double]$leg.Adjacent.x, [double]$leg.Adjacent.y)
            Magnitude = $magnitude
        }
    }
    if ($candidates.Count -gt 0) {
        $orderedCandidates = @(
            $candidates | Sort-Object -Property Magnitude, ConnectorId, EndpointX
        )
        return $orderedCandidates[0]
    }

    foreach ($fallback in @(
        [pscustomobject]@{ DeltaX = 0.35; DeltaY = 0.15 },
        [pscustomobject]@{ DeltaX = -0.35; DeltaY = 0.15 },
        [pscustomobject]@{ DeltaX = 0.35; DeltaY = -0.15 },
        [pscustomobject]@{ DeltaX = -0.35; DeltaY = -0.15 }
    )) {
        if (Test-TranslatedShapeWithinPage -Page $Page -RootShape $RootShape -DeltaX $fallback.DeltaX -DeltaY $fallback.DeltaY) {
            return [pscustomobject]@{
                DeltaX = [double]$fallback.DeltaX
                DeltaY = [double]$fallback.DeltaY
                Strategy = "standard_translation"
                ConnectorId = $null
                EndpointX = $null
                EndpointBefore = $null
                BendBefore = $null
                Magnitude = [Math]::Sqrt(
                    $fallback.DeltaX * $fallback.DeltaX + $fallback.DeltaY * $fallback.DeltaY
                )
            }
        }
    }
    throw "Shape cannot be moved safely inside the page $Stage."
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
        Assert-NativeRoutingPolicy -Page $page -Stage "after initial open"
        Assert-OrthogonalTerminalLegs -Page $page -Stage "after initial open"
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
            Assert-ShapeDrawingWithinTransform -RootShape $root -Label $label -Stage "before movement"
            Assert-StaticEndpointsMatchConnectionPoints -Page $page -RootShape $root -Label $label -Stage "before movement"
            Assert-StraightConnectorEnvelopes -Page $page -RootShape $root -Label $label -Stage "before movement"
            Assert-OrthogonalTerminalLegs -Page $page -Stage "before moving '$label'"

            $pinX = $root.CellsU("PinX")
            $pinY = $root.CellsU("PinY")
            $beforeX = [double]$pinX.ResultIU
            $beforeY = [double]$pinY.ResultIU
            $moveDelta = Get-PreferredMoveDelta -Page $page -RootShape $root -Stage "before moving '$label'"
            $expectedX = $beforeX + [double]$moveDelta.DeltaX
            $expectedY = $beforeY + [double]$moveDelta.DeltaY

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
            Assert-NativeRoutingPolicy -Page $page -Stage "after moving '$label'"
            Assert-OrthogonalTerminalLegs -Page $page -Stage "after moving '$label'"
            Assert-ShapeDrawingWithinTransform -RootShape $root -Label $label -Stage "after movement"
            Assert-StaticEndpointsMatchConnectionPoints -Page $page -RootShape $root -Label $label -Stage "after movement"
            Assert-StraightConnectorEnvelopes -Page $page -RootShape $root -Label $label -Stage "after movement"

            $visio.Undo()
            Assert-Near -Expected $beforeX -Actual ([double]$pinX.ResultIU) -Description "Shape '$label' PinX after undo"
            Assert-Near -Expected $beforeY -Actual ([double]$pinY.ResultIU) -Description "Shape '$label' PinY after undo"
            $signaturesAfterUndo = @(Get-NativeConnectionSignatures -Page $page -RootShape $root)
            Assert-SameConnectionSignatures -Label $label -Expected $signaturesBefore -Actual $signaturesAfterUndo -Stage "after undo"
            $endpointsAfterUndo = @(Get-NativeEndpointCoordinates -Page $page -RootShape $root)
            Assert-EndpointOffset -Label $label -Before $endpointsBefore -After $endpointsAfterUndo -DeltaX 0 -DeltaY 0 -Stage "after undo"
            Assert-NativeConnectionMetadata -Page $page -Stage "after undoing '$label'"
            Assert-NativeRoutingPolicy -Page $page -Stage "after undoing '$label'"
            Assert-OrthogonalTerminalLegs -Page $page -Stage "after undoing '$label'"
            Assert-ShapeDrawingWithinTransform -RootShape $root -Label $label -Stage "after undo"
            Assert-StaticEndpointsMatchConnectionPoints -Page $page -RootShape $root -Label $label -Stage "after undo"
            Assert-StraightConnectorEnvelopes -Page $page -RootShape $root -Label $label -Stage "after undo"

            $visio.Redo()
            Assert-Near -Expected $expectedX -Actual ([double]$pinX.ResultIU) -Description "Shape '$label' PinX after redo"
            Assert-Near -Expected $expectedY -Actual ([double]$pinY.ResultIU) -Description "Shape '$label' PinY after redo"
            $signaturesAfterRedo = @(Get-NativeConnectionSignatures -Page $page -RootShape $root)
            Assert-SameConnectionSignatures -Label $label -Expected $signaturesBefore -Actual $signaturesAfterRedo -Stage "after redo"
            $endpointsAfterRedo = @(Get-NativeEndpointCoordinates -Page $page -RootShape $root)
            Assert-EndpointOffset -Label $label -Before $endpointsAfter -After $endpointsAfterRedo -DeltaX 0 -DeltaY 0 -Stage "after redo"
            Assert-NativeConnectionMetadata -Page $page -Stage "after redoing '$label'"
            Assert-NativeRoutingPolicy -Page $page -Stage "after redoing '$label'"
            Assert-OrthogonalTerminalLegs -Page $page -Stage "after redoing '$label'"
            Assert-ShapeDrawingWithinTransform -RootShape $root -Label $label -Stage "after redo"
            Assert-StaticEndpointsMatchConnectionPoints -Page $page -RootShape $root -Label $label -Stage "after redo"
            Assert-StraightConnectorEnvelopes -Page $page -RootShape $root -Label $label -Stage "after redo"

            $moves += [ordered]@{
                label = $label
                root_shape_id = [int]$root.ID
                pin_before = @($beforeX, $beforeY)
                pin_after = @([double]$pinX.ResultIU, [double]$pinY.ResultIU)
                pin_after_undo = @($beforeX, $beforeY)
                pin_after_redo = @([double]$pinX.ResultIU, [double]$pinY.ResultIU)
                movement_delta = @([double]$moveDelta.DeltaX, [double]$moveDelta.DeltaY)
                movement_strategy = [string]$moveDelta.Strategy
                crossed_connector_id = $moveDelta.ConnectorId
                crossed_endpoint = $moveDelta.EndpointX
                endpoint_before_crossing = $moveDelta.EndpointBefore
                bend_before_crossing = $moveDelta.BendBefore
                native_connection_signatures = $signaturesBefore
                connector_endpoints_before = $endpointsBefore
                connector_endpoints_after = $endpointsAfterRedo
            }
        }

        $crossedTerminalBend = @(
            $moves | Where-Object { $_.movement_strategy -eq "cross_terminal_bend" }
        ).Count -gt 0
        if ($RequireBendCrossing -and -not $crossedTerminalBend) {
            throw "No requested shape could be moved safely across an orthogonal connector's terminal bend."
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
        Assert-NativeRoutingPolicy -Page $reopenedPage -Stage "after save and reopen"
        Assert-OrthogonalTerminalLegs -Page $reopenedPage -Stage "after save and reopen"

        foreach ($move in $moves) {
            $reopenedMatch = Find-TopLevelShapeByLabel -Page $reopenedPage -Label $move.label
            $reopenedRoot = $reopenedMatch.Root
            $reopenedSignatures = @(Get-NativeConnectionSignatures -Page $reopenedPage -RootShape $reopenedRoot)
            Assert-SameConnectionSignatures -Label $move.label -Expected ([string[]]$move.native_connection_signatures) -Actual $reopenedSignatures -Stage "after save and reopen"
            Assert-ShapeDrawingWithinTransform -RootShape $reopenedRoot -Label $move.label -Stage "after save and reopen"
            Assert-StaticEndpointsMatchConnectionPoints -Page $reopenedPage -RootShape $reopenedRoot -Label $move.label -Stage "after save and reopen"
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
            bend_crossing_required = [bool]$RequireBendCrossing
            terminal_bend_crossed = $crossedTerminalBend
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
