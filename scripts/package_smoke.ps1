param(
    [switch]$BuildInstaller
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist"
$work = Join-Path $root "build"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $dist, $work

pyinstaller --noconfirm --clean --onefile --windowed --name SwitchbladeLegacyCompatibility --distpath (Join-Path $dist "app") --workpath $work --specpath $work --collect-all app (Join-Path $root "app\ui.py")
$exe = Join-Path $dist "app\SwitchbladeLegacyCompatibility.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Owned application executable was not produced." }

if ($BuildInstaller) {
    $compiler = Get-Command ISCC.exe -ErrorAction Stop
    & $compiler.Source (Join-Path $root "installer\SwitchbladeLegacyCompatibility.iss")
    if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed." }
}
