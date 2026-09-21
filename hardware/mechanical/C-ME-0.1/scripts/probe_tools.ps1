# Read-only installation probe. Does NOT install, update, start hardware or edit CAD.
# Run from PowerShell: .\scripts\probe_tools.ps1
param([string]$OutputDirectory = (Join-Path $PSScriptRoot '..\reports'))
$ErrorActionPreference = 'Stop'
function Find-Candidates([string[]]$Commands, [string[]]$Patterns) {
    $paths = @()
    foreach ($name in $Commands) {
        $items = @(Get-Command $name -ErrorAction SilentlyContinue)
        foreach ($item in $items) { if ($item.Source) { $paths += $item.Source } }
    }
    foreach ($pattern in $Patterns) {
        $items = @(Get-Item -Path $pattern -ErrorAction SilentlyContinue)
        foreach ($item in $items) { if (-not $item.PSIsContainer) { $paths += $item.FullName } }
    }
    return @($paths | Sort-Object -Unique)
}
$pf = $env:ProgramFiles
$la = $env:LOCALAPPDATA
$definitions = @(
    @{name='Blender'; commands=@('blender.exe'); patterns=@("$pf\Blender Foundation\Blender*\blender.exe", "$la\Programs\Blender Foundation\Blender*\blender.exe")},
    @{name='FreeCAD'; commands=@('FreeCAD.exe','FreeCADCmd.exe','freecadcmd.exe'); patterns=@("$pf\FreeCAD*\bin\FreeCAD.exe", "$pf\FreeCAD*\bin\FreeCADCmd.exe", "$la\Programs\FreeCAD*\bin\FreeCAD.exe")},
    @{name='KiCad'; commands=@('kicad-cli.exe'); patterns=@("$pf\KiCad\*\bin\kicad-cli.exe", "$pf\KiCad\bin\kicad-cli.exe")}
)
$results=@()
foreach ($d in $definitions) {
    $paths=@(Find-Candidates $d.commands $d.patterns)
    $entries=@()
    foreach ($p in $paths) {
        $fi=Get-Item -LiteralPath $p
        $entries += [ordered]@{path=$p; file_version=$fi.VersionInfo.FileVersion; product_version=$fi.VersionInfo.ProductVersion}
    }
    $results += [ordered]@{tool=$d.name; candidates=$entries; status=$(if($paths.Count -gt 0){'FOUND_METADATA_ONLY'}else{'NOT_FOUND_IN_CHECKED_PATHS'}); runtime_cli_probe='NOT_RUN'}
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$out=Join-Path $OutputDirectory "LOCAL_TOOL_PATHS_$stamp.json"
[ordered]@{utc=$stamp; note='File metadata only; Codex must run the actual selected executable version/help separately. Missing here does not prove uninstalled.'; tools=$results} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Encoding UTF8
Write-Output $out
