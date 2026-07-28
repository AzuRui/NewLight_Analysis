param(
    [Parameter(Mandatory = $true)]
    [string]$SourceRoot,
    [Parameter(Mandatory = $true)]
    [string]$DestinationRoot,
    [string]$FallbackSourceRoot = ""
)

$source = (Resolve-Path -LiteralPath $SourceRoot).Path
$destination = [System.IO.Path]::GetFullPath($DestinationRoot)
$packages = @("einops", "efficientnet_pytorch", "dill", "cpuinfo")

New-Item -ItemType Directory -Force -Path $destination | Out-Null
foreach ($package in $packages) {
    $packageSource = Join-Path $source $package
    $sourceFiles = @()
    if (Test-Path -LiteralPath $packageSource -PathType Container) {
        $sourceFiles = @(
            Get-ChildItem -LiteralPath $packageSource -Recurse -File -Filter "*.py" |
                Where-Object { $_.FullName -notmatch "[\\/]tests?[\\/]" }
        )
    }
    if ($sourceFiles.Count -eq 0 -and $FallbackSourceRoot) {
        $packageSource = Join-Path ([System.IO.Path]::GetFullPath($FallbackSourceRoot)) $package
        if (Test-Path -LiteralPath $packageSource -PathType Container) {
            $sourceFiles = @(
                Get-ChildItem -LiteralPath $packageSource -Recurse -File -Filter "*.py" |
                    Where-Object { $_.FullName -notmatch "[\\/]tests?[\\/]" }
            )
        }
    }
    if ($sourceFiles.Count -eq 0) {
        throw "NeuSuite bundled dependency is missing: $packageSource"
    }
    $sourceFiles | ForEach-Object {
        $relative = $_.FullName.Substring($packageSource.Length).TrimStart("\")
        $target = Join-Path (Join-Path $destination $package) $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
}

Write-Host "Copied NeuSuite pure-Python runtime dependencies to $destination"
