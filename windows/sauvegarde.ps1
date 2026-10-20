<#
    Sauvegarde de la base et des pieces jointes.

    Essai :        .\windows\sauvegarde.ps1
    Automatique :  planifiez-le tous les jours a 20h avec le Planificateur
                   de taches (Action : powershell.exe -File <chemin>).
#>
param(
    [string] $DataDir = $(if ($env:DATA_DIR) { $env:DATA_DIR } else { "C:\ProgramData\GestionFournisseurs" }),
    [string] $Destination = "",
    [int]    $RetentionJours = 30
)

$ErrorActionPreference = "Stop"
if (-not $Destination) { $Destination = Join-Path $DataDir "sauvegardes" }
if (-not (Test-Path $Destination)) { New-Item -ItemType Directory -Path $Destination -Force | Out-Null }

$base = Join-Path $DataDir "gestion.db"
if (-not (Test-Path $base)) { Write-Host "Base introuvable : $base" -ForegroundColor Red; exit 1 }

$horodatage = Get-Date -Format "yyyyMMdd-HHmmss"
$dossier    = Join-Path $env:TEMP "gestion-$horodatage"
New-Item -ItemType Directory -Path $dossier -Force | Out-Null

# Copie coherente de la base, meme si l'application ecrit pendant ce temps.
$racine = Split-Path -Parent $PSScriptRoot
$python = Join-Path $racine ".venv\Scripts\python.exe"
& $python -c @"
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close(); src.close()
"@ $base (Join-Path $dossier "gestion.db")

$pieces = Join-Path $DataDir "pieces-jointes"
if (Test-Path $pieces) { Copy-Item $pieces -Destination $dossier -Recurse }

$archive = Join-Path $Destination "gestion-$horodatage.zip"
Compress-Archive -Path "$dossier\*" -DestinationPath $archive -Force
Remove-Item $dossier -Recurse -Force

Get-ChildItem $Destination -Filter "gestion-*.zip" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionJours) } |
    Remove-Item -Force

$taille = [math]::Round((Get-Item $archive).Length / 1MB, 1)
Write-Host "Sauvegarde ecrite : $archive ($taille Mo)" -ForegroundColor Green
