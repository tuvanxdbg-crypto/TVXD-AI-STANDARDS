<#
.SYNOPSIS
  Run the M01 acceptance tests from the repo root on the Windows machine.

.DESCRIPTION
  M01-09        tests/m01/check_no_secrets.py
  M01-01/07/08  tests/m01/m01_probe.py --mode surface   (server view; no login needed)
  M01-07        tests/m01/m01_lock.py surface --mode locked   (model-visible tools in the
                locked operating session: exactly the 4 approved, nothing else)
  M01-07/08     tests/m01/m01_lock.py surface --mode project  (ordinary sessions in this
                repo: no NotebookLM/Gemini server or tool at all)
  M01-02..06,10 tests/m01/m01_probe.py --mode full      (needs m01-login.ps1 first)
  M01-10 (LLM)  tests/m01/m01_10_run.py                 (claude -p, dontAsk mode)

  Python runs through `uv run --no-project --python 3.11`, so nothing is
  installed into a global Python. Raw evidence goes to tests/m01/evidence/local/
  (git-ignored); review it before transcribing into tests/m01/ACCEPTANCE.md.

  Fail fast: the first failing step stops the run and later steps do not start
  (in particular, no M01-10 LLM run after a failed probe). Only one run at a time:
  a second concurrent run exits at once (lock file in tests/m01/evidence/local/).

.EXAMPLE
  # before login: surface tests only
  powershell -ExecutionPolicy Bypass -File scripts\m01\m01-acceptance.ps1 -SurfaceOnly
  # after login, with the dedicated test notebook
  powershell -ExecutionPolicy Bypass -File scripts\m01\m01-acceptance.ps1 `
      -NotebookId <id> -SourceId <id> -InjectionSourceId <id>
#>
[CmdletBinding()]
param(
    [switch]$SurfaceOnly,
    [string]$NotebookId,
    [string]$SourceId,
    [string]$InjectionSourceId,
    [switch]$SkipLlm,
    [switch]$LlmSelfTest
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$userHome = $env:USERPROFILE
if (-not $userHome) { $userHome = $HOME }
# Same precondition as m01-login.ps1: the 0.15.1 server cannot create missing parent dirs.
New-Item -ItemType Directory -Force -Path (Join-Path $userHome '.tvxd-notebooklm-mcp-cli') | Out-Null

$py = @('run', '--no-project', '--python', '3.11')

function Run-Step([string]$name, [string[]]$argList) {
    Write-Host ''
    Write-Host ('==== {0}' -f $name)
    & uv @argList
    if ($LASTEXITCODE -ne 0) {
        throw ('FAILED STEP: {0} (exit code {1}). Stopped; later steps were not run.' -f $name, $LASTEXITCODE)
    }
}

# One acceptance run at a time on this machine (V-14). The handle is exclusive and the
# OS releases it when this process ends, even if it is killed, so no stale lock remains.
$evidenceDir = Join-Path $repo 'tests/m01/evidence/local'
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
$lockPath = Join-Path $evidenceDir 'm01-acceptance.lock'
try {
    $lock = [System.IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
} catch {
    Write-Host ('Cannot take the run lock {0}: {1}' -f $lockPath, $_.Exception.Message)
    Write-Host 'Another m01-acceptance.ps1 run is probably in progress. Wait for it; do not run acceptance concurrently.'
    exit 1
}

$failure = $null
Push-Location $repo
try {
    Run-Step 'M01-09 no secrets tracked' ($py + @('tests/m01/check_no_secrets.py'))

    if ($SurfaceOnly) {
        Run-Step 'M01-01/07/08 probe (surface)' ($py + @('tests/m01/m01_probe.py', '--mode', 'surface'))
    } else {
        $probe = $py + @('tests/m01/m01_probe.py', '--mode', 'full')
        if ($NotebookId) { $probe += @('--notebook-id', $NotebookId) }
        if ($SourceId) { $probe += @('--source-id', $SourceId) }
        if ($InjectionSourceId) { $probe += @('--injection-source-id', $InjectionSourceId) }
        Run-Step 'M01-01..08 + M01-10 data path (full)' $probe
    }

    # After the probe, so the uvx environment is already cached when Claude Code starts the server.
    Run-Step 'M01-07 Claude Code tool surface, locked session' ($py + @('tests/m01/m01_lock.py', 'surface', '--mode', 'locked'))
    Run-Step 'M01-07/08 Claude Code tool surface, ordinary sessions' ($py + @('tests/m01/m01_lock.py', 'surface', '--mode', 'project'))

    if ($LlmSelfTest) {
        Run-Step 'M01-10 harness self-test (offline, not evidence)' ($py + @('tests/m01/m01_10_run.py', '--self-test'))
    }
    if (-not $SkipLlm -and -not $SurfaceOnly) {
        if ($InjectionSourceId) {
            Run-Step 'M01-10 LLM data-boundary' ($py + @('tests/m01/m01_10_run.py', '--source-id', $InjectionSourceId))
        } else {
            Write-Host ''
            Write-Host '==== M01-10 LLM data-boundary: NOT_RUN (pass -InjectionSourceId)'
        }
    }
} catch {
    $failure = $_.Exception.Message
} finally {
    Pop-Location
    $lock.Dispose()
}

Write-Host ''
if ($failure) {
    Write-Host $failure
    exit 1
}
Write-Host 'All executed steps passed. Evidence: tests\m01\evidence\local\'
