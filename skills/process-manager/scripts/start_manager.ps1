param(
  [string]$Workspace = (Get-Location).Path,
  [string]$Config = "",
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"

function Resolve-AbsolutePath([string]$PathValue, [string]$Label) {
  if ([string]::IsNullOrWhiteSpace($PathValue)) {
    throw "$Label 不能为空"
  }
  $item = Resolve-Path -LiteralPath $PathValue -ErrorAction Stop
  return $item.Path
}

function Quote-Argument([string]$Value) {
  '"' + ($Value -replace '"', '\"') + '"'
}

$workspacePath = Resolve-AbsolutePath $Workspace "Workspace"
$skillRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$serverPath = Join-Path $skillRoot "scripts\manager_server.py"

if (-not (Test-Path -LiteralPath $serverPath)) {
  throw "缺少 manager_server.py：$serverPath"
}

if ([string]::IsNullOrWhiteSpace($Config)) {
  $configPath = Join-Path $workspacePath ".harness\process-manager\config.json"
} else {
  $configPath = Resolve-AbsolutePath $Config "Config"
}

if (-not (Test-Path -LiteralPath $configPath)) {
  throw "manager config 不存在，请先运行 pm_init.py：$configPath"
}

$configJson = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$stateRoot = Resolve-AbsolutePath ([string]$configJson.stateRoot) "stateRoot"
$pidFile = Join-Path $stateRoot "manager.pid"
$logsDir = Join-Path $stateRoot "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

if (Test-Path -LiteralPath $pidFile) {
  $oldPidText = (Get-Content -Raw -LiteralPath $pidFile).Trim()
  if ($oldPidText -match '^\d+$') {
    $oldProcess = Get-Process -Id ([int]$oldPidText) -ErrorAction SilentlyContinue
    if ($null -ne $oldProcess) {
      Write-Output "ALREADY_RUNNING pid=$oldPidText"
      exit 0
    }
  }
}

if ([string]::IsNullOrWhiteSpace($Python)) {
  $pythonCommand = Get-Command python -ErrorAction Stop
  $pythonPath = $pythonCommand.Source
} else {
  $pythonPath = Resolve-AbsolutePath $Python "Python"
}

$stdout = Join-Path $logsDir "manager.out.log"
$stderr = Join-Path $logsDir "manager.err.log"
$args = @(
  (Quote-Argument $serverPath),
  "--config",
  (Quote-Argument $configPath),
  "--stdout-log",
  (Quote-Argument $stdout),
  "--stderr-log",
  (Quote-Argument $stderr)
)

$process = Start-Process `
  -FilePath $pythonPath `
  -ArgumentList $args `
  -WorkingDirectory $workspacePath `
  -WindowStyle Hidden `
  -PassThru

$process.Id | Set-Content -LiteralPath $pidFile -Encoding ascii
Write-Output "STARTED pid=$($process.Id)"
