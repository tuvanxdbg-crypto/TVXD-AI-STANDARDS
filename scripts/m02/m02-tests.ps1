<#
.SYNOPSIS
  Run the M02 Standards Gateway offline tests (fixture data only) on Windows.

.DESCRIPTION
  1. M02 unit/contract tests: tests/m02/test_gateway_*.py (fake NotebookLM backend,
     fixture library under tests/m02/fixtures/library).
  2. M01 regression: tests/m01 checker controls, console-encoding tests, M01-09 secret scan.
  3. -WithClaude: real Claude Code checks against the fixture Gateway:
     model-visible surface (exactly the three Gateway tools) and the LLM data-boundary run.
     Uses Claude Code credits (a few cents). NotebookLM stays disabled.

  Nothing here contacts NotebookLM, reads the real Nextcloud library or changes M01 config.
  The script stops at the first failing step. Raw Claude evidence goes to
  tests/m02/evidence/local/ (git-ignored).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\m02\m02-tests.ps1
  powershell -ExecutionPolicy Bypass -File scripts\m02\m02-tests.ps1 -WithClaude
#>
[CmdletBinding()]
param(
    [switch]$WithClaude
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$py = @('run', '--no-project', '--python', '3.11')
$gw = @('run', '--no-project', '--python', '3.11', '--with', 'pyyaml==6.0.2', '--exclude-newer', '2026-10-03T00:00:00Z')

function Run-Step([string]$name, [string[]]$argList) {
    Write-Host ''
    Write-Host ('==== {0}' -f $name)
    & uv @argList
    if ($LASTEXITCODE -ne 0) {
        throw ('FAILED STEP: {0} (exit code {1}). Stopped; later steps were not run.' -f $name, $LASTEXITCODE)
    }
}

$failure = $null
Push-Location $repo
try {
    Run-Step 'M02 unit/contract tests (fixture, fake NotebookLM)' ($gw + @('python', '-m', 'unittest', 'discover', '-s', 'tests/m02', '-p', 'test_gateway_*.py'))
    Run-Step 'M01 regression: M01-10 checker controls' ($py + @('tests/m01/test_m01_10_llm_check.py'))
    Run-Step 'M01 regression: console encoding' ($py + @('tests/m01/test_m01_console.py'))
    Run-Step 'M01-09 secret scan' ($py + @('tests/m01/check_no_secrets.py'))
    if ($WithClaude) {
        if (-not $env:MCP_TIMEOUT) { $env:MCP_TIMEOUT = '120000' }   # this process only
        Run-Step 'M02 model-visible surface (real Claude Code, fixture Gateway)' ($gw + @('tests/m02/m02_surface.py', 'surface'))
        Run-Step 'M02 LLM data boundary (real Claude Code, fixture Gateway)' ($gw + @('tests/m02/m02_surface.py', 'llm'))
    }
} catch {
    $failure = $_.Exception.Message
} finally {
    Pop-Location
}

Write-Host ''
if ($failure) {
    Write-Host $failure
    exit 1
}
Write-Host 'All executed M02 steps passed (OFFLINE fixture validation only; not M02 overall PASS).'
