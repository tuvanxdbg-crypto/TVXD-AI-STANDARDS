<#
.SYNOPSIS
  M01 audit of the Windows machine that runs Claude Code.

.DESCRIPTION
  Does not modify tracked working-tree files or NotebookLM content. Side effects
  are limited to `git fetch` (updates remote-tracking refs), caches and state that
  `claude` and `uv` keep for themselves, and the output file below.
  Prints tool versions, repo state, existing NotebookLM MCP installs and which
  NotebookLM MCP servers Claude Code would load in THIS project. Output is also
  saved to tests/m01/evidence/local/ (git-ignored).

  Privacy: prints no environment values, no MCP env blocks, and only the
  claude mcp lines that mention notebook/gemini (other servers' args may hold
  tokens). Review the file before copying anything into ACCEPTANCE.md.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\m01\m01-audit.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$outDir = Join-Path $repo 'tests/m01/evidence/local'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$outFile = Join-Path $outDir ('m01-audit-{0}.txt' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
$lines = New-Object System.Collections.Generic.List[string]

function Say([string]$text) {
    $script:lines.Add($text)
    Write-Host $text
}

function First-Line([string]$exe, [string[]]$argList) {
    try {
        $out = & $exe @argList 2>&1 | Select-Object -First 1
        if ($null -eq $out) { return '(no output)' }
        return ($out | Out-String).Trim()
    } catch {
        return ('(error: {0})' -f $_.Exception.Message)
    }
}

$isWin = ($env:OS -eq 'Windows_NT')
$userHome = $env:USERPROFILE
if (-not $userHome) { $userHome = $HOME }

Say '== M01 WINDOWS AUDIT (no tracked-file or NotebookLM changes)'
Say ('utc: {0}' -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Say ('os: {0}' -f [System.Environment]::OSVersion.VersionString)
if ($isWin) {
    try { Say ('os_caption: {0}' -f (Get-CimInstance Win32_OperatingSystem).Caption) } catch { }
}
Say ('powershell: {0}' -f $PSVersionTable.PSVersion.ToString())

Say ''
Say '== TOOLS'
$tools = @(
    @{ n = 'claude'; a = @('--version') },
    @{ n = 'git'; a = @('--version') },
    @{ n = 'python'; a = @('--version') },
    @{ n = 'py'; a = @('--version') },
    @{ n = 'uv'; a = @('--version') },
    @{ n = 'uvx'; a = @('--version') },
    @{ n = 'nlm'; a = @('--version') },
    @{ n = 'notebooklm-mcp'; a = @('--help') }
)
foreach ($t in $tools) {
    $cmd = Get-Command $t.n -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $cmd) {
        Say ('{0,-15} NOT FOUND' -f $t.n)
    } elseif ($t.n -eq 'notebooklm-mcp') {
        Say ('{0,-15} {1}  (global install present; M01 does not use it)' -f $t.n, $cmd.Source)
    } else {
        Say ('{0,-15} {1}  |  {2}' -f $t.n, $cmd.Source, (First-Line $cmd.Source $t.a))
    }
}

Say ''
Say '== REPOSITORY'
Push-Location $repo
try {
    $branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
    $head = (& git rev-parse HEAD 2>$null)
    Say ('branch: {0}' -f $branch)
    Say ('head:   {0}' -f $head)
    $dirty = @(& git status --porcelain 2>$null).Count
    Say ('uncommitted entries: {0}' -f $dirty)
    & git fetch --quiet origin $branch 2>$null
    $remote = (& git rev-parse --verify --quiet ('refs/remotes/origin/{0}' -f $branch) 2>$null)
    if ($remote) {
        Say ('origin/{0}: {1}' -f $branch, $remote)
        $ab = (& git rev-list --left-right --count ('HEAD...origin/{0}' -f $branch) 2>$null)
        Say ('ahead/behind origin: {0}' -f $ab)
    } else {
        Say 'origin branch: not found (fetch failed or branch not pushed)'
    }
} finally {
    Pop-Location
}

Say ''
Say '== EXISTING NOTEBOOKLM MCP INSTALLS (informational, not modified)'
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    $uvTools = @(& uv tool list 2>$null | Where-Object { $_ -match 'notebooklm' })
    if ($uvTools.Count -gt 0) { $uvTools | ForEach-Object { Say ('uv tool: {0}' -f $_) } } else { Say 'uv tool: no notebooklm package installed globally' }
}
$defaultState = Join-Path $userHome '.notebooklm-mcp-cli'
Say ('default state dir used by other projects (~\.notebooklm-mcp-cli): {0}' -f (Test-Path $defaultState))
$m01State = Join-Path $userHome '.tvxd-notebooklm-mcp-cli'
Say ('M01 isolated state dir (~\.tvxd-notebooklm-mcp-cli): {0}' -f (Test-Path $m01State))
$profilesDir = Join-Path $m01State 'profiles'
if (Test-Path $profilesDir) {
    $names = @(Get-ChildItem -Directory $profilesDir | ForEach-Object { $_.Name })
    Say ('M01 profiles (names only): {0}' -f ($names -join ', '))
}

Say ''
Say '== NOTEBOOKLM MCP SERVERS CLAUDE CODE LOADS IN THIS PROJECT'
$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if ($claudeCmd) {
    Push-Location $repo
    try {
        $mcpLines = @(& claude mcp list 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -match '(?i)notebook|gemini' })
        if ($mcpLines.Count -eq 0) { Say '(no notebook/gemini server listed)' }
        foreach ($l in $mcpLines) { Say ('mcp list: {0}' -f $l) }
        $getLines = @(& claude mcp get gemini-notebook-mcp 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -match '^\s*(Scope|Status|Type|Command|Args):' })
        foreach ($l in $getLines) { Say ('mcp get gemini-notebook-mcp: {0}' -f $l.Trim()) }
    } finally {
        Pop-Location
    }
    Say 'EXPECTED for ordinary sessions: no notebook/gemini server listed by `claude mcp list`, and'
    Say '`claude mcp get gemini-notebook-mcp` shows Status: Rejected (disabledMcpjsonServers), set once with'
    Say '`uv run --no-project --python 3.11 tests/m01/m01_lock.py setup-local`.'
    Say 'NotebookLM is used only through scripts\m01\m01-session.ps1 (locked). Any other notebook/gemini server'
    Say '(user or local scope) must be removed for this project; m01_lock.py surface --mode project checks this.'
}

$lines | Set-Content -Path $outFile -Encoding UTF8
Write-Host ''
Write-Host ('audit saved: {0}' -f $outFile)
