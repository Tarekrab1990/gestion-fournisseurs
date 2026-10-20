<#
    Installation de l'application en service sur un PC Windows.

    Ce script :
      - cree l'environnement Python et installe les composants ;
      - genere une cle de session et l'enregistre au niveau machine ;
      - declare une tache planifiee qui demarre l'application au demarrage
        du PC, avant meme qu'un utilisateur ouvre sa session ;
      - ouvre le port dans le pare-feu pour le reseau local.

    A lancer une seule fois, en tant qu'administrateur :
        clic droit sur le fichier  ->  Executer avec PowerShell
    ou, depuis une console PowerShell ouverte en administrateur :
        Set-ExecutionPolicy -Scope Process Bypass -Force
        .\windows\installer-service.ps1

    Pour retirer l'installation : .\windows\desinstaller-service.ps1
#>

[CmdletBinding()]
param(
    [int]    $Port        = 8000,
    [string] $DataDir     = "C:\ProgramData\GestionFournisseurs",
    [string] $MotDePasseAdmin = "",
    [switch] $LocalUniquement    # n'ecoute que sur ce poste, pas sur le reseau
)

$ErrorActionPreference = "Stop"
$NomTache = "GestionFournisseurs"

function Titre($texte) { Write-Host "`n=== $texte ===" -ForegroundColor Cyan }
function Info($texte)  { Write-Host "    $texte" }
function Bon($texte)   { Write-Host "    $texte" -ForegroundColor Green }
function Souci($texte) { Write-Host "    $texte" -ForegroundColor Yellow }

# --- droits administrateur ---------------------------------------------
$identite = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identite.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Ce script doit etre lance en tant qu'administrateur." -ForegroundColor Red
    Write-Host "Clic droit sur PowerShell -> Executer en tant qu'administrateur, puis relancez."
    Read-Host "Appuyez sur Entree pour fermer"
    exit 1
}

$Racine = Split-Path -Parent $PSScriptRoot
Set-Location $Racine
Titre "Application : $Racine"

# --- Python -------------------------------------------------------------
Titre "Verification de Python"
$python = $null
foreach ($candidat in @("py", "python")) {
    $chemin = Get-Command $candidat -ErrorAction SilentlyContinue
    if ($chemin) {
        try {
            $version = & $candidat -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($version -match '^3\.(9|1[0-9])') { $python = $candidat; break }
        } catch { }
    }
}
if (-not $python) {
    Write-Host "Python 3.9 ou plus recent est introuvable." -ForegroundColor Red
    Write-Host "Installez-le depuis https://www.python.org/downloads/windows/"
    Write-Host "en cochant 'Add python.exe to PATH', puis relancez ce script."
    Read-Host "Appuyez sur Entree pour fermer"
    exit 1
}
Bon "Python detecte via '$python'"

# --- environnement virtuel ----------------------------------------------
Titre "Environnement Python"
$pythonVenv = Join-Path $Racine ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonVenv)) {
    Info "Creation de l'environnement..."
    & $python -m venv (Join-Path $Racine ".venv")
}
Info "Installation des composants..."
& $pythonVenv -m pip install --upgrade pip --quiet
& $pythonVenv -m pip install -r (Join-Path $Racine "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "Echec de l'installation des composants (acces a pypi.org ?)." -ForegroundColor Red
    exit 1
}
Bon "Composants installes"

$waitress = Join-Path $Racine ".venv\Scripts\waitress-serve.exe"
if (-not (Test-Path $waitress)) {
    Info "Installation du serveur waitress..."
    & $pythonVenv -m pip install waitress --quiet
}

# --- dossier de donnees ---------------------------------------------------
Titre "Dossier de donnees"
if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Path $DataDir -Force | Out-Null }
Bon "$DataDir"
Souci "C'est le seul dossier a sauvegarder : base, pieces jointes, cle de session."

# --- variables d'environnement machine ------------------------------------
Titre "Configuration"
function DefinirVariable($nom, $valeur) {
    [Environment]::SetEnvironmentVariable($nom, $valeur, "Machine")
    Set-Item -Path "Env:$nom" -Value $valeur
}

$cleExistante = [Environment]::GetEnvironmentVariable("SECRET_KEY", "Machine")
if ([string]::IsNullOrWhiteSpace($cleExistante)) {
    $octets = New-Object byte[] 36
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($octets)
    $cle = [Convert]::ToBase64String($octets).Replace('+','-').Replace('/','_').TrimEnd('=')
    DefinirVariable "SECRET_KEY" $cle
    Bon "Cle de session generee"
} else {
    Info "Cle de session deja definie, conservee"
}

DefinirVariable "DATA_DIR" $DataDir
DefinirVariable "COOKIE_SECURE" "0"
DefinirVariable "SESSION_HOURS" "10"
if ($MotDePasseAdmin) { DefinirVariable "ADMIN_PASSWORD" $MotDePasseAdmin }

$ecoute = if ($LocalUniquement) { "127.0.0.1" } else { "0.0.0.0" }
Info "Ecoute sur $ecoute port $Port"

# --- tache planifiee -------------------------------------------------------
Titre "Demarrage automatique"
$lanceur = Join-Path $PSScriptRoot "service-lancer.bat"
if (-not (Test-Path $lanceur)) {
    Write-Host "Fichier manquant : $lanceur" -ForegroundColor Red
    exit 1
}
DefinirVariable "GESTION_LISTEN" "$ecoute`:$Port"

schtasks /Query /TN $NomTache >$null 2>&1
if ($LASTEXITCODE -eq 0) {
    Info "Tache existante, remplacement..."
    schtasks /End    /TN $NomTache >$null 2>&1
    schtasks /Delete /TN $NomTache /F >$null 2>&1
}

$action    = New-ScheduledTaskAction -Execute "cmd.exe" `
                -Argument "/c `"$lanceur`"" -WorkingDirectory $Racine
$declencheur = New-ScheduledTaskTrigger -AtStartup
$compte    = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$reglages  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries -StartWhenAvailable `
                -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
                -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $NomTache -Action $action -Trigger $declencheur `
    -Principal $compte -Settings $reglages `
    -Description "Application de gestion des fournisseurs et des paiements" | Out-Null
Bon "Tache planifiee '$NomTache' creee (demarrage au boot)"

# --- pare-feu ---------------------------------------------------------------
Titre "Pare-feu"
$regle = "Gestion fournisseurs (port $Port)"
Get-NetFirewallRule -DisplayName $regle -ErrorAction SilentlyContinue | Remove-NetFirewallRule
if (-not $LocalUniquement) {
    New-NetFirewallRule -DisplayName $regle -Direction Inbound -Protocol TCP `
        -LocalPort $Port -Action Allow -Profile Domain,Private | Out-Null
    Bon "Port $Port ouvert sur les profils Domaine et Prive"
    Souci "Le profil Public reste ferme, volontairement."
} else {
    Info "Mode local : aucun port ouvert"
}

# --- demarrage ---------------------------------------------------------------
Titre "Demarrage"
schtasks /Run /TN $NomTache | Out-Null
Start-Sleep -Seconds 6

try {
    $reponse = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/sante" -TimeoutSec 10
    Bon "Application demarree, version $($reponse.version)"
} catch {
    Souci "L'application ne repond pas encore. Consultez $DataDir\service.log"
}

$fichierMdp = Join-Path $DataDir "MOT_DE_PASSE_INITIAL.txt"
Titre "Termine"
Write-Host ""
Write-Host "  Depuis ce poste  : http://127.0.0.1:$Port" -ForegroundColor White
if (-not $LocalUniquement) {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 |
           Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
           Select-Object -First 1).IPAddress
    Write-Host "  Depuis le reseau : http://$ip`:$Port" -ForegroundColor White
}
Write-Host ""
if (Test-Path $fichierMdp) {
    Write-Host "  Identifiants de premiere connexion :" -ForegroundColor Yellow
    Get-Content $fichierMdp | ForEach-Object { Write-Host "      $_" }
    Write-Host "  Supprimez ce fichier apres la premiere connexion :" -ForegroundColor Yellow
    Write-Host "      $fichierMdp"
}
Write-Host ""
Write-Host "  Journal    : $DataDir\service.log"
Write-Host "  Arreter    : schtasks /End /TN $NomTache"
Write-Host "  Redemarrer : schtasks /Run /TN $NomTache"
Write-Host "  Desinstaller : .\windows\desinstaller-service.ps1"
Write-Host ""
Read-Host "Appuyez sur Entree pour fermer"
