[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskPidFile=Join-Path $taskRoot '.runtime\app-process.json'
if (!(Test-Path -LiteralPath $taskPidFile)) { Write-Output 'No project-managed app process is recorded.'; exit 0 }
$taskState=Get-Content -LiteralPath $taskPidFile -Raw | ConvertFrom-Json
$taskProcess=Get-Process -Id $taskState.pid -ErrorAction SilentlyContinue
if (!$taskProcess) { Write-Output 'Recorded app process is already stopped.'; exit 0 }
if ($taskProcess.StartTime.ToUniversalTime().Ticks -ne ([datetime]$taskState.started_at).ToUniversalTime().Ticks) { throw 'PID was reused; refusing to stop a different process.' }
$taskCommand=Get-CimInstance Win32_Process -Filter "ProcessId=$($taskState.pid)"
if ($taskCommand.CommandLine -notmatch 'observatory\.cli.+serve') { throw 'Process command does not match the project app; refusing to stop it.' }
Stop-Process -Id $taskState.pid
Wait-Process -Id $taskState.pid -Timeout 10 -ErrorAction SilentlyContinue
Write-Output 'Project app stopped. PostgreSQL remains available.'
