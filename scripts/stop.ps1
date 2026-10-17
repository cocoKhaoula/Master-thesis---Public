# Stop a command started with scripts\start.ps1:
#   powershell -ExecutionPolicy Bypass -File scripts\stop.ps1 loadgen
# For the campaign, run `lambda-rca recover` afterwards in case a fault is still active.
param([Parameter(Mandatory = $true)] [string] $Command)
$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root "logs\$Command.pid"
if (-not (Test-Path $pidFile)) { Write-Host "no running '$Command' recorded"; exit 0 }
$id = [int](Get-Content $pidFile)
# stops cmd.exe and the lambda-rca process it started
& taskkill.exe /PID $id /T /F | Out-Null
Remove-Item $pidFile
Write-Host "stopped '$Command' (process $id)"
