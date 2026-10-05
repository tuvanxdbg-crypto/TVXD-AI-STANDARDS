<#
.SYNOPSIS
  M01 owner-only step: sign in to NotebookLM for THIS project only.

.DESCRIPTION
  Uses the same pinned launcher as .mcp.json (uvx, notebooklm-mcp-cli 0.15.1,
  dependency cutoff 2026-10-03) with a project-dedicated state directory and
  profile, so the login is isolated from any other project on this machine:

    NOTEBOOKLM_MCP_CLI_PATH = %USERPROFILE%\.tvxd-notebooklm-mcp-cli
    NLM_PROFILE             = tvxd-m01

  The variables are set for this PowerShell process only (nothing is written to
  the user or machine environment). `nlm login` opens a dedicated browser
  profile under that state directory. Sign in there yourself, including MFA.
  The saved login uses protected storage (Windows Credential Manager key).

  Never paste passwords, cookies or tokens into chat, GitHub or files.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\m01\m01-login.ps1
  powershell -ExecutionPolicy Bypass -File scripts\m01\m01-login.ps1 -CheckOnly
#>
[CmdletBinding()]
param(
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$userHome = $env:USERPROFILE
if (-not $userHome) { $userHome = $HOME }
$state = Join-Path $userHome '.tvxd-notebooklm-mcp-cli'
$profileName = 'tvxd-m01'
$uvxArgs = @('--python', '3.11', '--exclude-newer', '2026-10-03T00:00:00Z', '--from', 'notebooklm-mcp-cli==0.15.1')

if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    throw 'uvx not found on PATH. Install uv first (see docs/M01_NOTEBOOKLM_READONLY.md), then reopen PowerShell.'
}

# notebooklm-mcp-cli 0.15.1 creates its state dir without parents=True; create it up front.
New-Item -ItemType Directory -Force -Path $state | Out-Null
$env:NOTEBOOKLM_MCP_CLI_PATH = $state
$env:NLM_PROFILE = $profileName

Write-Host ('state dir : {0}' -f $state)
Write-Host ('profile   : {0}' -f $profileName)
Write-Host 'package   : notebooklm-mcp-cli==0.15.1 (via uvx, isolated environment)'
& uvx @uvxArgs nlm --version

if (-not $CheckOnly) {
    Write-Host ''
    Write-Host '>>> A browser window will open. Sign in to the Google account that owns the NotebookLM notebooks.'
    Write-Host '>>> Complete MFA in the browser. Do not share passwords, cookies or tokens with anyone.'
    & uvx @uvxArgs nlm login --profile $profileName --storage protected
    if ($LASTEXITCODE -ne 0) { throw ('nlm login exited with code {0}' -f $LASTEXITCODE) }
}

Write-Host ''
Write-Host '== login check (M01-02 pre-check)'
& uvx @uvxArgs nlm login --check --profile $profileName
