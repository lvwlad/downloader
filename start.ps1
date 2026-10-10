param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    Write-Host 'Create .venv and install src/requirements.txt first. See README.md.'
    exit 1
}
Write-Host "Toksave: http://127.0.0.1:$Port"
& $projectPython -m uvicorn main:app --app-dir src --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
