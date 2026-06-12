param(
  [string]$Workspace = (Get-Location).Path,
  [string]$Config = ""
)

$ErrorActionPreference = "Stop"

function Resolve-AbsolutePath([string]$PathValue, [string]$Label) {
  if ([string]::IsNullOrWhiteSpace($PathValue)) {
    throw "$Label 不能为空"
  }
  $item = Resolve-Path -LiteralPath $PathValue -ErrorAction Stop
  return $item.Path
}

$workspacePath = Resolve-AbsolutePath $Workspace "Workspace"

if ([string]::IsNullOrWhiteSpace($Config)) {
  $configPath = Join-Path $workspacePath ".harness\process-manager\config.json"
} else {
  $configPath = Resolve-AbsolutePath $Config "Config"
}

if (-not (Test-Path -LiteralPath $configPath)) {
  throw "manager config 不存在：$configPath"
}

$configJson = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$stateRoot = Resolve-AbsolutePath ([string]$configJson.stateRoot) "stateRoot"
$pidFile = Join-Path $stateRoot "manager.pid"

if (-not (Test-Path -LiteralPath $pidFile)) {
  Write-Output "NOT_RUNNING"
  exit 0
}

$pidRaw = Get-Content -Raw -LiteralPath $pidFile
if ($null -eq $pidRaw) {
  $pidText = ""
} else {
  $pidText = $pidRaw.Trim()
}
if ([string]::IsNullOrWhiteSpace($pidText)) {
  Write-Output "NOT_RUNNING"
  exit 0
}
if ($pidText -notmatch '^\d+$') {
  Clear-Content -LiteralPath $pidFile
  throw "manager.pid 内容不是 PID：$pidText"
}

$process = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
if ($null -eq $process) {
  Clear-Content -LiteralPath $pidFile
  Write-Output "NOT_RUNNING"
  exit 0
}

Stop-Process -Id ([int]$pidText) -Force
Start-Sleep -Milliseconds 300

if (Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue) {
  throw "STOP_TIMEOUT pid=$pidText"
}

Clear-Content -LiteralPath $pidFile
Write-Output "STOPPED pid=$pidText"
