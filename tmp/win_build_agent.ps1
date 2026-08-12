$ErrorActionPreference = "Stop"
$env:Path = "E:\Python311;E:\Python311\Scripts;E:\tools\nodejs;" + $env:Path

$Root = "E:\work\sigtrades"
$Agent = Join-Path $Root "clients\relay-agent"
$Releases = Join-Path $Root "data\agent-releases"
$Py = "E:\Python311\python.exe"
$Wheels = "E:\tools\win-wheels"

function PipInstall([string[]]$pkgs) {
  & $Py -m pip install --no-index --find-links=$Wheels @pkgs
  if ($LASTEXITCODE -ne 0) { throw "pip install failed: $($pkgs -join ' ')" }
}

if (-not (Test-Path (Join-Path $Agent "build\build_win.py"))) { throw "Agent source missing" }
if (-not (Test-Path $Wheels)) { throw "Wheelhouse missing at $Wheels" }

Write-Host "==> Python:" (& $Py --version)
New-Item -ItemType Directory -Force -Path $Releases | Out-Null
Set-Location $Agent

Write-Host "==> Offline pip install from $Wheels ..."
PipInstall @("pip","setuptools","wheel")
PipInstall @("pyinstaller","pywebview","Pillow","pystray","ib_async","futu-api","websockets","httpx","aiohttp","pythonnet","pydantic")
PipInstall @("-e",(Join-Path $Root "packages\core"),"-e",(Join-Path $Root "packages\protocol"),"-e",".")

Write-Host "==> Verify imports..."
& $Py -c "import PyInstaller, webview, pystray, PIL, ib_async, futu; print('imports_ok')"
if ($LASTEXITCODE -ne 0) { throw "import check failed" }

if (-not (Test-Path (Join-Path $Agent "ui\dist\index.html"))) { throw "UI dist missing" }
Write-Host "==> UI dist present, skip npm"

Write-Host "==> Icons + PyInstaller..."
& $Py (Join-Path $Agent "build\make_icons.py")
if ($LASTEXITCODE -ne 0) { throw "make_icons failed" }

$Pyi = Join-Path $Agent "build\pyi"
$Dist = Join-Path $Agent "dist"
if (Test-Path $Pyi) { Remove-Item -Recurse -Force $Pyi }
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }

$Spec = Join-Path $Agent "build\sigtrades_agent.spec"
& $Py -m PyInstaller $Spec --noconfirm --distpath $Dist --workpath $Pyi
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$DistDir = Join-Path $Agent "dist\sigtrades-agent"
if (-not (Test-Path (Join-Path $DistDir "sigtrades-agent.exe"))) { throw "Missing dist exe" }

Copy-Item -Force (Join-Path $Agent "build\windows\Install.ps1") (Join-Path $DistDir "Install.ps1")
Copy-Item -Force (Join-Path $Agent "build\windows\setup.bat") (Join-Path $DistDir "setup.bat")
Copy-Item -Force (Join-Path $Agent "build\windows\INSTALL.txt") (Join-Path $DistDir "INSTALL.txt")

$init = Get-Content (Join-Path $Agent "sigtrades_agent\__init__.py") -Raw
if ($init -match '__version__\s*=\s*"([^"]+)"') { $Version = $Matches[1] } else { $Version = "0.1.8" }

$Out = Join-Path $Releases "sigtrades-agent-windows-v$Version.zip"
$Alias = Join-Path $Releases "sigtrades-agent-windows.zip"
if (Test-Path $Out) { Remove-Item -Force $Out }
if (Test-Path $Alias) { Remove-Item -Force $Alias }

Write-Host "==> Zip $Out (python zipfile; avoid Compress-Archive file locks)"
Start-Sleep -Seconds 2
$zipPy = @'
import zipfile
from pathlib import Path
src = Path(r"__SRC__")
out = Path(r"__OUT__")
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for p in src.rglob("*"):
        if p.is_file():
            zf.write(p, arcname=str(Path("sigtrades-agent") / p.relative_to(src)))
print(out, out.stat().st_size)
'@
$zipPy = $zipPy.Replace("__SRC__", $DistDir.Replace("\", "/")).Replace("__OUT__", $Out.Replace("\", "/"))
$zipPyPath = "E:\tools\_zip_agent_tmp.py"
Set-Content -Path $zipPyPath -Value $zipPy -Encoding UTF8
& $Py $zipPyPath
if ($LASTEXITCODE -ne 0) { throw "zip failed" }
Copy-Item -Force $Out $Alias

Get-Item $Out | Format-List FullName, Length, LastWriteTime
Write-Host "BUILD_OK version=$Version path=$Out"
