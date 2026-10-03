<#
.SYNOPSIS
  Run the M01 acceptance tests from the repo root on the Windows machine.

.DESCRIPTION
  M01-09        tests/m01/check_no_secrets.py
  M01-01/07/08  tests/m01/m01_probe.py --mode surface   (no login needed)
  M01-02..06,10 tests/m01/m01_probe.py --mode full      (needs m01-login.ps1 first)
  M01-10 (LLM)  tests/m01/m01_10_run.py                 (claude -p, dontAsk mode)

  Python runs through `uv run --no-project --python 3.11`, so nothing is
  installed into a global Python. Raw evidence goes to tests/m01/evidence/local/
  (git-ignored); review it before transcribing into tests/m01/ACCEPTANCE.md.

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
$failed = @()

function Run-Step([string]$name, [string[]]$argList) {
    Write-Host ''
    Write-Host ('==== {0}' -f $name)
    & uv @argList
    if ($LASTEXITCODE -ne 0) { $script:failed += $name }
}

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
} finally {
    Pop-Location
}

Write-Host ''
if ($failed.Count -gt 0) {
    Write-Host ('FAILED STEPS: {0}' -f ($failed -join '; '))
    exit 1
}
Write-Host 'All executed steps passed. Evidence: tests\m01\evidence\local\'
