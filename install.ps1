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
    $Version = "0.1.0b1"
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
        Write-Host "  uv tool install imagehearth-mcp==$Version"
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
    Write-Host "Installing $Package..."
    uv tool install $Package

    if ($LASTEXITCODE -ne 0 -and $FromPyPI) {
        # The same release, as a wheel on GitHub, in case PyPI doesn't have it.
        $Package = "$Docs/releases/download/v$Version/imagehearth_mcp-$Version-py3-none-any.whl"
        Write-Host "Not available from PyPI. Trying the GitHub release instead..."
        Write-Host "Installing $Package..."
        uv tool install $Package
    }

    if ($LASTEXITCODE -ne 0) {
        Show-Failure "Can't install $Package. Check your network connection and try again."
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

    if (($env:Path -split ";") -notcontains $BinDir) {
        Write-Host "To use imagehearth-mcp by name, run: uv tool update-shell"
    }
}

Install-ImageHearth
