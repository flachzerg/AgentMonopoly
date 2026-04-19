param(
  [ValidateSet("start", "restart", "stop", "status")]
  [string]$Mode = "restart"
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RunDir = Join-Path $RootDir ".run"
$BackendPort = if ($env:BACKEND_PORT) { [int]$env:BACKEND_PORT } else { 8000 }
$FrontendPort = if ($env:FRONTEND_PORT) { [int]$env:FRONTEND_PORT } else { 5173 }
$FrontendExtraPorts = if ($env:FRONTEND_EXTRA_PORTS) { $env:FRONTEND_EXTRA_PORTS -split "\s+" } else { @("5174", "5175") }
$BackendLog = Join-Path $RunDir "backend.log"
$BackendErrLog = Join-Path $RunDir "backend.err.log"
$FrontendLog = Join-Path $RunDir "frontend.log"
$FrontendErrLog = Join-Path $RunDir "frontend.err.log"
$BackendPidFile = Join-Path $RunDir "backend.pid"
$FrontendPidFile = Join-Path $RunDir "frontend.pid"

$DefaultAgentOptionsRel = "backend/config/agent_options.local.json"
$DeepseekOptionsRel = "backend/config/deepseek_agent_config.json"
$TemplateOptionsRel = "backend/config/agent_options.placeholder.json"

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

function Resolve-AgentOptionsFile {
  if ($env:AGENT_OPTIONS_FILE) { return $env:AGENT_OPTIONS_FILE }
  $candidates = @($DefaultAgentOptionsRel, $DeepseekOptionsRel, $TemplateOptionsRel)
  foreach ($candidate in $candidates) {
    if (Test-Path (Join-Path $RootDir $candidate)) { return $candidate }
  }
  return $TemplateOptionsRel
}

function Resolve-PythonExe {
  $candidates = @(
    (Join-Path $RootDir ".venv-Hackathon\Scripts\python.exe"),
    (Join-Path $RootDir "backend\.venv\Scripts\python.exe")
  )
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) { return $candidate }
  }
  return "python"
}

function Stop-PidFile([string]$PidFile) {
  if (-not (Test-Path $PidFile)) { return }
  $pidText = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($pidText) {
    Stop-Process -Id ([int]$pidText) -Force -ErrorAction SilentlyContinue
  }
  Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Stop-Port([int]$Port) {
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if (-not $conns) { return }
  $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($id in $pids) {
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
  }
}

function Stop-ByPattern([string]$Pattern) {
  $targets = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$Pattern*" } | Select-Object -ExpandProperty ProcessId -Unique
  foreach ($id in $targets) {
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
  }
}

function Stop-All {
  Stop-PidFile $BackendPidFile
  Stop-PidFile $FrontendPidFile
  Stop-Port $BackendPort
  Stop-Port $FrontendPort
  foreach ($extra in $FrontendExtraPorts) {
    if ($extra) { Stop-Port ([int]$extra) }
  }
  Stop-ByPattern "uvicorn app.main:app"
  Stop-ByPattern "vite --host"
}

function Start-Backend {
  $pythonExe = Resolve-PythonExe
  $agentOptions = Resolve-AgentOptionsFile
  Write-Output "Starting backend on :$BackendPort"
  Write-Output "Using AGENT_OPTIONS_FILE=$agentOptions"
  $env:AGENT_OPTIONS_FILE = $agentOptions
  $proc = Start-Process -FilePath $pythonExe `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$BackendPort", "--reload") `
    -WorkingDirectory (Join-Path $RootDir "backend") `
    -RedirectStandardOutput $BackendLog `
    -RedirectStandardError $BackendErrLog `
    -PassThru
  Set-Content -Path $BackendPidFile -Value $proc.Id
}

function Start-Frontend {
  Write-Output "Starting frontend on :$FrontendPort"
  $proc = Start-Process -FilePath "npx.cmd" `
    -ArgumentList @("vite", "--host", "0.0.0.0", "--port", "$FrontendPort") `
    -WorkingDirectory (Join-Path $RootDir "frontend") `
    -RedirectStandardOutput $FrontendLog `
    -RedirectStandardError $FrontendErrLog `
    -PassThru
  Set-Content -Path $FrontendPidFile -Value $proc.Id
}

function Show-Status {
  Write-Output "Backend log:  $BackendLog"
  Write-Output "Frontend log: $FrontendLog"
  Write-Output "Backend listeners:"
  Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue | Format-Table -AutoSize | Out-String | Write-Output
  Write-Output "Frontend listeners:"
  Get-NetTCPConnection -LocalPort $FrontendPort -State Listen -ErrorAction SilentlyContinue | Format-Table -AutoSize | Out-String | Write-Output
}

switch ($Mode) {
  "start" {
    Start-Backend
    Start-Frontend
  }
  "restart" {
    Stop-All
    Start-Backend
    Start-Frontend
  }
  "stop" {
    Stop-All
  }
  "status" {
    Show-Status
  }
}

Write-Output "Done. Backend: http://localhost:$BackendPort  Frontend: http://localhost:$FrontendPort"
Write-Output "Logs:"
Write-Output "  $BackendLog"
Write-Output "  $BackendErrLog"
Write-Output "  $FrontendLog"
Write-Output "  $FrontendErrLog"
