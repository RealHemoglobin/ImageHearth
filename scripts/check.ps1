# Verificación local en Windows: mismos pasos que check.sh.
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv with its official installer (https://astral.sh/uv)..."
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Set-Location (Join-Path $PSScriptRoot "..")

function Invoke-Checked {
    & $args[0] $args[1..($args.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Failed: $($args -join ' ')" }
}

Invoke-Checked uv sync --locked
Invoke-Checked uv run ruff check .
Invoke-Checked uv run pytest

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $tmp | Out-Null

try {
    Invoke-Checked uv build --wheel --out-dir "$tmp\dist"
    Invoke-Checked uv venv -q "$tmp\env"
    $python = "$tmp\env\Scripts\python.exe"
    $wheel = (Get-ChildItem "$tmp\dist\*.whl").FullName
    Invoke-Checked uv pip install -q --python $python $wheel pytest

    # Fuera del repositorio, para que no se importe src/.
    Push-Location $tmp
    try {
        & $python -c "import imagehearth_mcp, sys; print(imagehearth_mcp.__file__); sys.exit('site-packages' not in imagehearth_mcp.__file__)"
        if ($LASTEXITCODE -ne 0) { throw "The package was not imported from site-packages" }
    } finally {
        Pop-Location
    }

    $repo = (Get-Location).Path
    Invoke-Checked $python -m pytest "$repo\tests"
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
