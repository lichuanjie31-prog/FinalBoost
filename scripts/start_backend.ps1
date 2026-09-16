param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $projectRoot 'backend')
if (-not $env:GRADING_MODE) { $env:GRADING_MODE = 'mock' }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
