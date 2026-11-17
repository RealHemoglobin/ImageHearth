# ImageHearth installer for Windows. Read it before running it:
#   1. Checks the system and that there is a terminal to ask you questions.
#   2. Installs uv with its official installer, if it is missing.
#   3. Installs imagehearth-mcp, pinned to the version below.
#   4. Runs `setup`, which shows disk space and licenses before downloading,
#      and `connect --detect`, which asks before changing any agent.
# It never asks for administrator rights and never accepts a license for you.
#
# Everything is inside a function, so a cut-off download can't run half a script.
# It uses return instead of exit, which would close the window with `irm | iex`.

function Install-ImageHearth {
    $Version = "1.0.0"
    $Docs = "https://github.com/RealHemoglobin/ImageHearth"

    function Show-Failure($Message) {
        Write-Host "Error: $Message" -ForegroundColor Red
    }

    if ($env:OS -ne "Windows_NT") {
        Show-Failure "This script is for Windows. On Linux, see $Docs#installation."
        return
    }

    if (-not [Environment]::Is64BitOperatingSystem) {
        Show-Failure "ImageHearth needs 64-bit Windows."
        return
    }

    if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) {
        Show-Failure "No terminal available, so setup can't ask you to accept the model licenses. Nothing was changed."
        Write-Host "Without a terminal, install it yourself:"
        Write-Host "  uv tool install --python 3.13 imagehearth-mcp==$Version"
        Write-Host "  imagehearth-mcp setup --non-interactive"
        Write-Host "That command tells you which options it needs to continue. See $Docs/blob/main/llms-install.md."
        return
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        # Where the official installer leaves uv; this window doesn't know it yet.
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "Installing uv with its official installer (https://astral.sh/uv)..."
        # In its own process, as uv documents: the policy applies only to that process.
        powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"

        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            Show-Failure "Can't install uv. Check your network connection and try again, or install it by hand: https://docs.astral.sh/uv/getting-started/installation/"
            return
        }
    }

    # From a clone of the repository, install that code; with IMAGEHEARTH_INSTALL_SOURCE,
    # a local wheel; otherwise, the pinned version from PyPI.
    $Package = "imagehearth-mcp==$Version"
    $FromPyPI = $true
    if ($env:IMAGEHEARTH_INSTALL_SOURCE) {
        $Package = $env:IMAGEHEARTH_INSTALL_SOURCE
        $FromPyPI = $false
    } elseif ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "pyproject.toml"))) {
        $Package = $PSScriptRoot
        $FromPyPI = $false
    }
    # Windows can't replace a program that is running. Agents keep imagehearth-mcp
    # open while they run, and an update fails halfway and leaves it unusable.
    $ToolDir = (uv tool dir) 2>$null
    $Running = @()
    if ($ToolDir) {
        $Running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
            $_.Path -and ($_.Path -like (Join-Path $ToolDir "imagehearth-mcp\*") -or $_.Path -like "*\imagehearth-mcp.exe")
        })
    }
    if ($Running.Count -gt 0) {
        Write-Host "ImageHearth is running ($($Running.Count) processes), probably started by an agent:"
        $Running | ForEach-Object { Write-Host "  $($_.Id) $($_.Path)" }
        Write-Host "Windows can't update it while it runs. Close your agents (Claude Desktop, Claude Code, Codex...) or let me stop it."
        $Answer = Read-Host "Stop these processes now? [y/N]"
        if ($Answer -notmatch "^[yYsS]") {
            Show-Failure "Nothing was changed. Close the agents that use ImageHearth and run this again."
            return
        }
        $Running | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }

    Write-Host "Installing $Package..."
    uv tool install --python 3.13 $Package

    if ($LASTEXITCODE -ne 0 -and $FromPyPI) {
        # The same release, as a wheel on GitHub, in case PyPI doesn't have it.
        $Package = "$Docs/releases/download/v$Version/imagehearth_mcp-$Version-py3-none-any.whl"
        Write-Host "Could not install from PyPI. Trying the GitHub release instead..."
        Write-Host "Installing $Package..."
        uv tool install --python 3.13 $Package
    }

    if ($LASTEXITCODE -ne 0) {
        Show-Failure "Can't install $Package. Read uv's error above: a network failure, or a program still running from the old installation (close your agents). If the command is damaged, run: uv tool install --python 3.13 --force $Package"
        return
    }

    # It may not be in PATH yet.
    $BinDir = uv tool dir --bin
    $Command = Join-Path $BinDir "imagehearth-mcp.exe"

    & $Command setup

    if ($LASTEXITCODE -ne 0) {
        Show-Failure "Setup did not finish. Run this to continue where it stopped: & `"$Command`" setup"
        return
    }

    & $Command connect --detect

    if ($LASTEXITCODE -ne 0) {
        Show-Failure "Setup finished, but connecting your agents failed. Try again with: & `"$Command`" connect --detect"
        return
    }

    Write-Host ""
    Write-Host "Done. Restart your agent and ask it for an image."
    Write-Host "Check the installation at any time with: & `"$Command`" doctor"

    # A new session reads the saved user PATH, not this window's.
    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($UserPath -split ";") -notcontains $BinDir) {
        Write-Host ""
        Write-Host "$BinDir is not in your PATH. Running: uv tool update-shell"
        uv tool update-shell
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")

        if (($UserPath -split ";") -notcontains $BinDir) {
            Write-Host "A new terminal may still not find imagehearth-mcp. Add the directory yourself:"
            Write-Host "  [Environment]::SetEnvironmentVariable('Path', `"`$([Environment]::GetEnvironmentVariable('Path', 'User'));$BinDir`", 'User')"
            return
        }
    }

    if (($env:Path -split ";") -notcontains $BinDir) {
        Write-Host ""
        Write-Host "Open a new PowerShell window to use imagehearth-mcp by name."
    }
}

Install-ImageHearth
