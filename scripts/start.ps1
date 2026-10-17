# Start a long-running lambda-rca command as an independent background process.
# The process is created by Windows (WMI), not as a child of this terminal, so it keeps
# running when the terminal, the editor or the chat session is closed.
# Output goes to logs\<command>.log.
#
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 loadgen
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 campaign --limit 3 --reps 1
#
# Stop it again with:  powershell -ExecutionPolicy Bypass -File scripts\stop.ps1 loadgen
param(
    [Parameter(Mandatory = $true, Position = 0)] [string] $Command,
    [Parameter(ValueFromRemainingArguments = $true)] [string[]] $Rest
)
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root ".venv\Scripts\lambda-rca.exe"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs "$Command.log"
$cmdArgs = (@($Command) + $Rest) -join ' '
$line = "cmd.exe /c `"`"$exe`" $cmdArgs >> `"$log`" 2>&1`""
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $line; CurrentDirectory = $root }
if ($r.ReturnValue -ne 0) { Write-Host "failed to start (code $($r.ReturnValue))"; exit 1 }
Set-Content -Path (Join-Path $logs "$Command.pid") -Value $r.ProcessId
Write-Host "started 'lambda-rca $cmdArgs' (process $($r.ProcessId)); log: logs\$Command.log"
