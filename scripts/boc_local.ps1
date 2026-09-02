# Relevo local del BOC de Cantabria.
# El Gobierno de Cantabria no responde a IPs de fuera de España, así que este script descarga el BOC desde
# este equipo, guarda el volcado JSON en data/fuentes/boc_cantabria/ y lo sube al repositorio. Un push en esa
# carpeta dispara el workflow de GitHub Actions, que procesa los anuncios y publica la web.
#
# Programador de tareas (diario, p. ej. 08:15):
#   powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\boc_local.ps1"

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$log = Join-Path $PSScriptRoot "boc_local.log"
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -Append -Encoding utf8 $log

$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) { $python = (Get-Command python).Source }
$env:PYTHONIOENCODING = "utf-8"

try {
    git pull -q --rebase origin main 2>&1 | Out-File -Append -Encoding utf8 $log
    & $python -m observatorio.cli fetch --days 10 2>&1 | Out-File -Append -Encoding utf8 $log
    if ($LASTEXITCODE -ne 0) { throw "fetch devolvió $LASTEXITCODE" }
    git add data/fuentes
    $cambios = git status --porcelain data/fuentes
    if ($cambios) {
        git commit -q -m "BOC Cantabria: volcado local $(Get-Date -Format yyyy-MM-dd)" 2>&1 | Out-File -Append -Encoding utf8 $log
        git push -q origin main 2>&1 | Out-File -Append -Encoding utf8 $log
        "subidos: $(($cambios | Measure-Object).Count) ficheros" | Out-File -Append -Encoding utf8 $log
    } else {
        "sin cambios" | Out-File -Append -Encoding utf8 $log
    }
} catch {
    "ERROR: $_" | Out-File -Append -Encoding utf8 $log
    exit 1
}
