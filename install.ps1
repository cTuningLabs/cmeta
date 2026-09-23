<#
    cMeta installer that installs cMeta FROM THIS DIRECTORY - not from PyPI,
    not from git.

      powershell -ExecutionPolicy Bypass -File install.ps1
      powershell -ExecutionPolicy Bypass -File install.ps1 -WithDeps
      install.bat                       # same thing, via cmd

    Use it after copying a cMeta source tree onto a machine (rclone, rsync,
    scp, a USB stick): it installs the package sitting next to this script, so
    the machine runs exactly the code you copied rather than whatever happens
    to be released. To install the released or the git version instead, use the
    installer on the website:

      powershell -ExecutionPolicy ByPass -c "irm https://cTuning.ai/project/cmeta/cmeta.install/install.ps1 | iex"

    NETWORK: only cMeta itself comes from this directory. Its dependencies
    (pyyaml, requests, tabulate, ...) and uv are still fetched from the
    network, so PyPI and astral.sh have to be reachable. Nothing needs
    administrator rights unless -WithDeps is used.

    Copyright (C) 2025-2026 Grigori Fursin and cTuning Labs.
    Licensed under Apache-2.0 - see https://github.com/cTuningLabs/cmeta

    NOTE FOR EDITORS: unlike the website installer this script CANNOT be piped
    into iex - it installs its own directory, and $PSScriptRoot is empty in a
    pipe. That is checked explicitly in Get-SourceDir. It also means parameter
    binding always works here, so this script has none of the website
    installer's CMETA_INSTALL_* environment-variable plumbing, which exists
    purely to pass options through a pipe.
#>

[CmdletBinding()]
param(
    [switch] $WithDeps,
    [switch] $Editable,
    [string] $Extras     = '',
    [switch] $NoExtras,
    [string] $CmetaHome  = '',
    [string] $CmetaHome2 = '',
    [switch] $NoHome,
    [switch] $Aops,
    [switch] $NoModifyPath,
    [switch] $DryRun,
    [switch] $Quiet,
    [switch] $Help
)

$ErrorActionPreference = 'Stop'

$script:UvInstallUrl = 'https://astral.sh/uv/install.ps1'
$script:AopsRef      = 'cTuningLabs@cmeta-aops'

# What setuptools needs in order to build this tree at all. pyproject.toml
# declares `readme = "README.md"` and
# `license-files = ["LICENSE", "COPYRIGHT", "NOTICE"]`, so a tree copied with a
# filter that took only cmeta/ and pyproject.toml fails deep inside the build
# with an obscure message. Checked up front instead - see Test-SourceTree.
$script:RequiredFiles = @('pyproject.toml', 'README.md', 'LICENSE', 'COPYRIGHT', 'NOTICE')

# ------------------------------------------------------------------ output

function Say  { param([string]$m) if (-not $script:Q) { Write-Host $m } }
function Step { param([string]$m) if (-not $script:Q) { Write-Host ''; Write-Host "==> $m" -ForegroundColor Cyan } }
function Warn { param([string]$m) Write-Warning $m }
function Fail { param([string]$m) Write-Error "cmeta-install: $m"; exit 1 }

function Have { param([string]$n) return [bool](Get-Command $n -ErrorAction SilentlyContinue) }

# Everything that touches the machine goes through here, so -DryRun is a
# complete preview rather than an approximation.
# NOTE: the parameter is deliberately NOT called $Args - that is a PowerShell
# automatic variable, so a parameter of that name never receives the caller's
# values and every command printed its name with no arguments at all.
#
# -AllowFail leaves the exit code in $LASTEXITCODE for the caller to judge,
# for a command whose non-zero codes do not all mean failure (winget).
function Run {
    param([string]$Exe, [string[]]$CmdArgs, [switch]$AllowFail)
    Say "     > $Exe $($CmdArgs -join ' ')"
    if ($script:DryRunMode) { $global:LASTEXITCODE = 0; return }
    & $Exe @CmdArgs
    if ($LASTEXITCODE -ne 0 -and -not $AllowFail) { Fail "$Exe exited with $LASTEXITCODE" }
}

function Show-Usage {
    Write-Host @'
cMeta installer - installs from THIS directory (Windows)

Usage:
  powershell -ExecutionPolicy Bypass -File install.ps1 [options]
  install.bat [options]

Options:
  -WithDeps        also install git with winget (the only step needing admin)
  -Editable        install in editable mode: the installed cMeta keeps
                   pointing at this directory, so re-copying the tree updates
                   it with no reinstall. Do NOT use it if this directory is
                   temporary.
  -Extras a,b      pip extras (default: server, needed by cserver)
  -NoExtras        install the bare package with no extras at all
  -CmetaHome  P    set CMETA_HOME to P (default: %USERPROFILE%\CMETA).
                   Always wins, even inside an activated venv.
  -CmetaHome2 P    set CMETA_HOME2 instead: the same home, except that an
                   activated virtual environment is still allowed to win
  -NoHome          set neither; let cMeta resolve the home on its own
  -Aops            also plug in the cmeta-aops automation repository
  -NoModifyPath    do not touch PATH or any persisted variable
  -DryRun          print every command without running anything
  -Quiet           only report errors
  -Help            this text

What it needs:
  This directory must be a complete cMeta source tree - pyproject.toml,
  README.md, LICENSE, COPYRIGHT, NOTICE and the cmeta\ package. Plus
  PowerShell 5.1+ and network access to astral.sh (for uv) and PyPI (for the
  dependencies). Python is NOT required - uv fetches its own.

  If you copied this tree with a filter, make sure it took those five files
  and not just cmeta\ and pyproject.toml.
'@
}

# ------------------------------------------------------------------ options

# A home path written for the other shell. -File hands its arguments over as
# literal strings, so cmd's %USERPROFILE% arrives unexpanded when the command
# is pasted into PowerShell, and PowerShell's $HOME or ~ when it is pasted into
# cmd - and would otherwise become a directory literally named that.
function Expand-HomePath {
    param([string]$p)
    if (-not $p) { return $p }
    $p = [Environment]::ExpandEnvironmentVariables($p)
    if ($p -match '^(~|\$HOME|\$env:USERPROFILE)(?=$|[\\/])') {
        $p = $env:USERPROFILE + $p.Substring($Matches[0].Length)
    }
    return $p
}

function Resolve-Options {
    $script:WithDepsMode = $WithDeps.IsPresent
    $script:EditableMode = $Editable.IsPresent
    $script:NoHomeMode   = $NoHome.IsPresent
    $script:AopsMode     = $Aops.IsPresent
    $script:NoPathMode   = $NoModifyPath.IsPresent
    $script:DryRunMode   = $DryRun.IsPresent
    $script:Q            = $Quiet.IsPresent
    # "server" by default: cserver is a first-class part of cMeta, and without
    # this extra `cx app run cserver` cannot start - there is no uvicorn to run
    # it with, and a uv tool environment has no pip to add one afterwards, so
    # the only cure is a reinstall. -NoExtras installs the bare package.
    $script:ExtrasList   = if ($Extras) { $Extras } else { 'server' }
    if ($NoExtras.IsPresent) { $script:ExtrasList = '' }

    $h  = Expand-HomePath $CmetaHome
    $h2 = Expand-HomePath $CmetaHome2
    if ($h -and $h2) {
        Fail '-CmetaHome and -CmetaHome2 are mutually exclusive'
    }
    if ($h2) {
        $script:HomeVar = 'CMETA_HOME2'; $script:HomeDir = $h2
    } else {
        $script:HomeVar = 'CMETA_HOME'
        $script:HomeDir = if ($h) { $h } else { Join-Path $env:USERPROFILE 'CMETA' }
    }
}

# ------------------------------------------------------------------ source tree

# The directory this script lives in is what gets installed. Deliberately not
# the current location: running it by full path from anywhere installs the tree
# next to the script, never the folder you happen to be sitting in.
function Get-SourceDir {
    if (-not $PSScriptRoot) {
        Fail @'
this installer has to run as a FILE, because it installs its own directory.
                   $PSScriptRoot is empty, which means it was piped (irm ... |
                   iex) or dot-sourced from a string. Run it like this:

                     powershell -ExecutionPolicy Bypass -File install.ps1

                   To install the released version from the internet instead,
                   use the website installer, which is designed to be piped.
'@
    }
    $script:SrcDir = $PSScriptRoot
}

function Test-SourceTree {
    $missing = @()
    foreach ($f in $script:RequiredFiles) {
        if (-not (Test-Path (Join-Path $script:SrcDir $f))) { $missing += $f }
    }
    if (-not (Test-Path (Join-Path $script:SrcDir 'cmeta\__init__.py'))) {
        $missing += 'cmeta\__init__.py'
    }
    if ($missing.Count -eq 0) { return }

    Fail @"
this is not a complete cMeta source tree.
                   Directory: $script:SrcDir
                   Missing:   $($missing -join ' ')

                   pyproject.toml points setuptools at README.md and at
                   LICENSE/COPYRIGHT/NOTICE, so the build needs all of them
                   even though they are not code. If you copied this tree with
                   a filter, widen it - with rclone, for example:

                     --whitelist=/cmeta/,/pyproject.toml,/README.md,/LICENSE,/COPYRIGHT,/NOTICE
"@
}

# ------------------------------------------------------------------ steps

function Add-LocalBin {
    # uv installs into %USERPROFILE%\.local\bin. This session needs it on PATH
    # straight away, because the very next step calls uv.
    $d = Join-Path $env:USERPROFILE '.local\bin'
    if ((Test-Path $d) -and ($env:PATH -notlike "*$d*")) {
        $env:PATH = "$d;$env:PATH"
    }
}

# Bring PATH entries that an installer has just written to the registry into
# this session. The Git installer adds C:\Program Files\Git\cmd to the machine
# PATH, but a shell that is already running never sees it - so without this the
# -Aops step, a few seconds after installing git, found no git and skipped.
function Update-SessionPath {
    $known = @($env:PATH -split ';' | Where-Object { $_ })
    foreach ($scope in 'Machine', 'User') {
        $p = [Environment]::GetEnvironmentVariable('Path', $scope)
        if (-not $p) { continue }
        foreach ($d in ($p -split ';')) {
            if (-not $d) { continue }
            $d = [Environment]::ExpandEnvironmentVariables($d)
            if ($known -notcontains $d) { $env:PATH = "$env:PATH;$d"; $known += $d }
        }
    }
}

function Find-Git {
    if (Have git) { return $true }
    Update-SessionPath
    return (Have git)
}

# Exit codes with which winget reports that the package is already there.
$script:WingetAlreadyInstalled = @(
    -1978335189,    # 0x8A15002B  installed, and no newer version to upgrade to
    -1978335135     # 0x8A150061  installed (--no-upgrade)
)

# A missing or failing git is a warning, not the end of the install: cMeta
# itself does not need it, only `cx repo get` does, and every later step says
# so again and names the command to run once git is there.
function Install-Deps {
    Step 'Installing system packages (git)'
    if (Find-Git) {
        Say "     git is already installed ($(& git --version))"
        return
    }
    if (-not (Have winget)) {
        Warn ('-WithDeps installs git with winget, which is not available here: ' +
              'Windows Server and older Windows 10 builds ship without it, and on a ' +
              'new machine it can take a few minutes after the first sign-in, or an ' +
              'update of "App Installer" from the Microsoft Store. Continuing without ' +
              'git - install it from https://git-scm.com/download/win and then run: ' +
              "cx repo get $script:AopsRef")
        return
    }
    # --source winget: without it winget also queries the Microsoft Store
    # source, and on a machine where that fails - "0x8a15005e: The server
    # certificate did not match any of the expected values", certificate
    # pinning broken by an HTTPS-inspecting antivirus or proxy - it refuses to
    # install the package it has just found in the winget source, and asks for
    # --source. winget takes one --id per invocation.
    Run 'winget' @('install', '-e', '--id', 'Git.Git', '--source', 'winget',
                   '--accept-source-agreements', '--accept-package-agreements') -AllowFail
    $code = $LASTEXITCODE
    if ($script:DryRunMode) { return }
    if ($code -ne 0 -and $script:WingetAlreadyInstalled -notcontains $code) {
        Warn (("winget could not install git (exit code {0}, 0x{0:X8}). Continuing " +
               "without it - install git from https://git-scm.com/download/win, open " +
               "a new shell and run: cx repo get {1}") -f $code, $script:AopsRef)
        return
    }
    if (-not (Find-Git)) {
        Warn "git is installed but not visible in this shell yet. Open a new shell and run: cx repo get $script:AopsRef"
    }
}

function Install-Uv {
    if (Have uv) {
        Step 'uv is already installed'
        return
    }
    Step 'Installing uv'
    Say "     > irm $script:UvInstallUrl | iex"
    if (-not $script:DryRunMode) {
        if ($script:NoPathMode) { $env:UV_NO_MODIFY_PATH = '1' }
        Invoke-Expression (Invoke-RestMethod -Uri $script:UvInstallUrl)
        Add-LocalBin
        if (-not (Have uv)) {
            Fail 'uv was installed but is not on PATH. Open a new shell and re-run.'
        }
    }
}

function Install-Cmeta {
    Step "Installing cMeta from $script:SrcDir"

    # With extras the argument becomes a PEP 508 "extras @ path" requirement,
    # because "uv tool install C:\dir[server]" is read as a name rather than a
    # path with extras.
    $target = if ($script:ExtrasList) {
        "cmeta[$script:ExtrasList] @ $script:SrcDir"
    } else {
        $script:SrcDir
    }

    # --force so that re-running upgrades in place: the version in
    # cmeta\version.py does not change between local edits, and uv would
    # otherwise decide there is nothing to do.
    if ($script:EditableMode) {
        Say '     (editable: the install keeps pointing at this directory)'
        Run 'uv' @('tool', 'install', '--force', '--editable', $target)
    } else {
        Run 'uv' @('tool', 'install', '--force', $target)
    }

    if ($script:NoPathMode) {
        Say '     (skipping uv tool update-shell: -NoModifyPath)'
    } else {
        Run 'uv' @('tool', 'update-shell')
    }
    Add-LocalBin
}

function Set-CmetaHome {
    if ($script:NoHomeMode) {
        Step 'Leaving the cMeta home unset (-NoHome)'
        Say '     cMeta will resolve it: an active venv wins, else ~/CMETA.'
        return
    }
    Step "Pointing cMeta at $script:HomeDir via $script:HomeVar"
    if ($script:HomeVar -eq 'CMETA_HOME') {
        Say '     A global command does not imply a global home: with CMETA_HOME'
        Say '     unset, an activated virtual environment captures it instead.'
    } else {
        Say '     CMETA_HOME2 is the fallback home: an activated virtual'
        Say '     environment still takes precedence over it.'
    }

    Set-Item -Path "env:$script:HomeVar" -Value $script:HomeDir

    if ($script:NoPathMode) {
        Say '     (not persisted: -NoModifyPath)'
        return
    }
    $existing = [Environment]::GetEnvironmentVariable($script:HomeVar, 'User')
    if ($existing) {
        Say "     $script:HomeVar is already set for this user ($existing) - leaving it"
        return
    }
    Say "     > [Environment]::SetEnvironmentVariable('$script:HomeVar', '$script:HomeDir', 'User')"
    if (-not $script:DryRunMode) {
        # 'User' scope, not 'Machine': no administrator rights needed. Note
        # that this does not affect already-running processes, which is why the
        # epilogue asks for a new shell.
        [Environment]::SetEnvironmentVariable($script:HomeVar, $script:HomeDir, 'User')
    }
}

function Add-Repos {
    if (-not $script:AopsMode) { return }
    Step 'Adding the cmeta-aops automation repository'
    if (-not $script:DryRunMode -and -not (Find-Git)) {
        Warn "git is not installed, so cx repo get cannot clone. Skipping. Install git (or re-run with -WithDeps), then: cx repo get $script:AopsRef"
        return
    }
    Run 'cx' @('repo', 'get', $script:AopsRef)
}

function Test-Install {
    Step 'Verifying'
    if ($script:DryRunMode) { Say '     > cx --version'; return }
    if (-not (Have cx)) {
        Fail 'cMeta installed but cx is not on PATH. Open a new shell and try cx --version.'
    }
    if ($script:Q) { & cx --version | Out-Null } else { & cx --version }
    if (-not (Find-Git)) {
        Warn 'git is not installed. cMeta works, but "cx repo get" needs git to clone content repositories.'
    }
}

# Whether Windows long paths are on. The cmeta-aops tasks offer to switch them
# on - with an administrator prompt - the first time they run without them, so
# the epilogue says so, and the prompt does not come as a surprise.
function Test-LongPaths {
    try {
        $v = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' `
                               -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled
        return ($v -eq 1)
    } catch {
        return $false
    }
}

function Show-Epilogue {
    if ($script:Q) { return }
    Write-Host @"

cMeta is installed from $script:SrcDir

  Open a new shell (so PATH and $script:HomeVar are picked up), then:

    cx --version                        # version, and the home it resolved
    cx repo list                        # what is plugged in
    cx repo get $script:AopsRef    # the reference automation repository

  Re-copy this tree and re-run this script to update.
  Remove it with:  uv tool uninstall cmeta

  Docs: https://github.com/cTuningLabs/cmeta/blob/main/docs/installation.md
"@
    if (-not (Test-LongPaths)) {
        Write-Host @'
  Windows long paths are off. The cmeta-aops tasks offer to switch them on the
  first time they run, with an administrator prompt; to do it yourself, turn on
  Settings > System > Advanced > "Enable long paths".
'@
    }
}

# ------------------------------------------------------------------ main

function Invoke-Main {
    $script:Q = $Quiet.IsPresent
    if ($Help.IsPresent) { Show-Usage; return }

    Resolve-Options
    Get-SourceDir
    Test-SourceTree

    Step "cMeta installer - Windows, PowerShell $($PSVersionTable.PSVersion)"
    Say  "     source: $script:SrcDir"
    if ($script:DryRunMode) { Say '     (dry run: nothing will be changed)' }

    if ($script:WithDepsMode) { Install-Deps }
    Install-Uv
    Install-Cmeta
    Set-CmetaHome
    Add-Repos
    Test-Install
    Show-Epilogue
}

Invoke-Main
