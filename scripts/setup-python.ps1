param([ValidateSet('cpu', 'cu128')][string]$Backend = 'cpu')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'
    }
    if (-not (Test-Path '.venv/Scripts/python.exe')) {
        uv venv --python 3.12.13 .venv
        if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
    }
    & .venv/Scripts/python.exe -c "import sys; assert sys.version_info[:2] == (3, 12), 'Python 3.12 required'"
    if ($LASTEXITCODE -ne 0) { throw 'Existing venv uses the wrong Python; use a separate environment' }
    uv pip install --python .venv/Scripts/python.exe "torch==2.11.0+$Backend" "torchvision==0.26.0+$Backend" --index-url "https://download.pytorch.org/whl/$Backend"
    if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed' }
    uv pip install --python .venv/Scripts/python.exe -r server/requirements.txt -c server/constraints-windows-py312.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    uv pip check --python .venv/Scripts/python.exe
    if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed' }
} finally { Pop-Location }
