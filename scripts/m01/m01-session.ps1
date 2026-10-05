<#
.SYNOPSIS
  M01 operating path: the only supported way to use NotebookLM from Claude Code in this repo.

.DESCRIPTION
  1. Preflight, fail closed: tests/m01/m01_lock.py surface --mode locked must PASS,
     i.e. Claude Code shows the model exactly the four approved NotebookLM tools
     and nothing else (no Bash, PowerShell, Read, Grep, Glob, Write, Edit, WebFetch,
     no other MCP server or connector).
  2. Starts an interactive Claude Code session with the same locked arguments:
       --permission-mode dontAsk --tools= --allowedTools <4 NotebookLM tools>
       --mcp-config .mcp.json --strict-mcp-config
     In this session Claude cannot run commands, read or write files, or fetch URLs.

  Ordinary Claude Code sessions in this repo must not load NotebookLM at all; run
  `uv run --no-project --python 3.11 tests/m01/m01_lock.py setup-local` once, and
  `surface --mode project` (part of m01-acceptance.ps1) verifies it.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\m01\m01-session.ps1
  powershell -ExecutionPolicy Bypass -File scripts\m01\m01-session.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$userHome = $env:USERPROFILE
if (-not $userHome) { $userHome = $HOME }
# notebooklm-mcp-cli 0.15.1 cannot create missing parent dirs of its state dir.
New-Item -ItemType Directory -Force -Path (Join-Path $userHome '.tvxd-notebooklm-mcp-cli') | Out-Null

$py = @('run', '--no-project', '--python', '3.11')
Push-Location $repo
try {
    Write-Host '== preflight: locked tool surface'
    & uv @py 'tests/m01/m01_lock.py' 'surface' '--mode' 'locked'
    if ($LASTEXITCODE -ne 0) {
        throw 'Preflight FAILED: the locked session would expose more or other tools than the four approved ones. Not starting Claude Code.'
    }

    $lockedArgs = @(& uv @py 'tests/m01/m01_lock.py' 'args')
    if ($LASTEXITCODE -ne 0 -or -not ($lockedArgs -contains '--tools=') -or -not ($lockedArgs -contains '--strict-mcp-config')) {
        throw 'Could not read the locked argument list. Not starting Claude Code.'
    }

    Write-Host ''
    Write-Host ('claude ' + ($lockedArgs -join ' '))
    if ($DryRun) { return }
    Write-Host 'Starting locked M01 session (NotebookLM read tools only; no shell, file or web tools).'
    if (-not $env:MCP_TIMEOUT) { $env:MCP_TIMEOUT = '120000' }   # this process only
    & claude @lockedArgs
} finally {
    Pop-Location
}
