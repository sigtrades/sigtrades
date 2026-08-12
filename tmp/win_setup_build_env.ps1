$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path E:\tools | Out-Null
New-Item -ItemType Directory -Force -Path E:\work | Out-Null

if (-not (Test-Path E:\Python311\python.exe)) {
  Write-Host "Downloading Python 3.11.9..."
  Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile E:\tools\python311.exe
  Write-Host "Installing Python 3.11 to E:\Python311 (no PATH change)..."
  $p = Start-Process -FilePath E:\tools\python311.exe -ArgumentList @(
    "/quiet",
    "InstallAllUsers=0",
    "TargetDir=E:\Python311",
    "PrependPath=0",
    "Include_test=0",
    "Include_launcher=0",
    "AssociateFiles=0"
  ) -Wait -PassThru
  Write-Host "Python installer exit:" $p.ExitCode
}

if (-not (Test-Path E:\Python311\python.exe)) {
  throw "Python 3.11 install failed"
}
& E:\Python311\python.exe --version

if (-not (Test-Path E:\tools\nodejs\node.exe)) {
  Write-Host "Downloading Node 20 LTS zip..."
  Invoke-WebRequest -Uri "https://nodejs.org/dist/v20.18.1/node-v20.18.1-win-x64.zip" -OutFile E:\tools\node.zip
  Expand-Archive -Path E:\tools\node.zip -DestinationPath E:\tools -Force
  if (Test-Path E:\tools\nodejs) {
    Remove-Item -Recurse -Force E:\tools\nodejs
  }
  Rename-Item E:\tools\node-v20.18.1-win-x64 E:\tools\nodejs
}

& E:\tools\nodejs\node.exe --version
& E:\tools\nodejs\npm.cmd --version
Write-Host "DONE"
