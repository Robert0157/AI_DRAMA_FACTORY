$ErrorActionPreference = 'Stop'
$root = 'F:\AI_DRAMA_FACTORY'
$venvPython = "$root\venv\Scripts\python.exe"
$output = "$root\scripts\gear1_prod\distrokid_new_codegen.py"
$url = 'https://distrokid.com/new/'

Write-Host 'Launching Playwright codegen for new DistroKid flow...' -ForegroundColor Cyan
Write-Host "Output: $output" -ForegroundColor Yellow
Write-Host "URL:    $url" -ForegroundColor Yellow

& $venvPython -m playwright codegen --target python -o $output $url
