<#
.SYNOPSIS
    Stage the NeuSuite2p CPU model (weights + vendored Ultralytics runtime) into the
    build cache so NewLight_Analysis.spec can package the CPU fast-ROI path.

.DESCRIPTION
    The model only ships inside the unified GPU addon archive, and every /rebuild wipes
    dist\, so the archive members are unpacked once into NewLight_BuildCache\NeuSuite2p.
    Existing complete staging is reused unless -Force is given.

.PARAMETER Force
    Re-extract even when the cache already looks complete.

.PARAMETER SourceZip
    Explicit GPU_Addon_CUDA.zip to extract from. Otherwise the repo copy and the
    ProgramData download cache are tried in that order.
#>
param(
    [switch]$Force,
    [string]$SourceZip
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $RepoRoot
$Destination = Join-Path $WorkspaceRoot 'NewLight_BuildCache\NeuSuite2p'

function Test-Staged {
    param([string]$Path)
    $weights = Join-Path $Path 'segment_model.pt'
    $runtime = Join-Path $Path 'method\ultralytics'
    return ((Test-Path -LiteralPath $weights) -and ((Get-Item -LiteralPath $weights).Length -gt 1MB) -and
            (Test-Path -LiteralPath $runtime))
}

if ((Test-Staged $Destination) -and -not $Force) {
    Write-Host "NeuSuite2p build source already staged: $Destination"
    return
}

$candidates = @()
if ($SourceZip) { $candidates += $SourceZip }
$candidates += (Join-Path $RepoRoot 'GPU_Addon_CUDA.zip')
$candidates += (Join-Path $env:ProgramData 'NewLight_Analysis\GPU_Addon_CUDA.zip')
$archive = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $archive) {
    throw "GPU_Addon_CUDA.zip was not found in $($candidates -join ', '). Restore it or download the unified GPU addon."
}

$Tar = Join-Path $env:SystemRoot 'System32\tar.exe'
if (-not (Test-Path -LiteralPath $Tar)) {
    throw "bsdtar is required to read $archive; System32\tar.exe was not found."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
if (Test-Path -LiteralPath $Destination) {
    $staleLeaf = (Split-Path -Leaf $Destination) + '-stale-' + (Get-Date -Format yyyyMMddHHmmss)
    Write-Host "Moving the previous copy aside as $staleLeaf"
    Rename-Item -LiteralPath $Destination -NewName $staleLeaf
}

Write-Host "Extracting GPU_Addon/NeuSuite2p from $archive"
& $Tar -xf $archive --strip-components 1 -C (Split-Path -Parent $Destination) 'GPU_Addon/NeuSuite2p/*'
if ($LASTEXITCODE -ne 0) {
    throw "tar.exe exited with $LASTEXITCODE while extracting $archive"
}

if (-not (Test-Staged $Destination)) {
    throw "Extraction did not produce a complete model at $Destination"
}

$weights = Get-Item -LiteralPath (Join-Path $Destination 'segment_model.pt')
$runtimeSize = (Get-ChildItem -LiteralPath (Join-Path $Destination 'method') -Recurse -File |
    Measure-Object -Property Length -Sum).Sum
Write-Host ("Staged NeuSuite2p at {0}: {1:N1} MB weights, {2:N1} MB runtime" -f `
    $Destination, ($weights.Length / 1MB), ($runtimeSize / 1MB))
