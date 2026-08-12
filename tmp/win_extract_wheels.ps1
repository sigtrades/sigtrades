$ErrorActionPreference = "Stop"
Write-Host "Extracting win-wheels.tgz..."
if (Test-Path E:\tools\win-wheels) { Remove-Item -Recurse -Force E:\tools\win-wheels }
if (Test-Path E:\tools\wheels) { Remove-Item -Recurse -Force E:\tools\wheels }
& tar -xzf E:\tools\win-wheels.tgz -C E:\tools
if (-not (Test-Path E:\tools\win-wheels)) {
  throw "Extract failed: E:\tools\win-wheels missing"
}
Rename-Item E:\tools\win-wheels wheels
$count = (Get-ChildItem E:\tools\wheels).Count
Write-Host "EXTRACT_OK count=$count"
Get-ChildItem E:\tools\wheels | Select-Object -First 8 -ExpandProperty Name
