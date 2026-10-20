<#
    Retire le demarrage automatique et la regle de pare-feu.
    Les donnees ne sont PAS supprimees : elles restent dans DATA_DIR.

    Clic droit -> Executer avec PowerShell, en administrateur.
#>
$ErrorActionPreference = "SilentlyContinue"
$NomTache = "GestionFournisseurs"

$identite = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identite.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "A lancer en tant qu'administrateur." -ForegroundColor Red
    Read-Host "Entree pour fermer"; exit 1
}

schtasks /End    /TN $NomTache | Out-Null
schtasks /Delete /TN $NomTache /F | Out-Null
Write-Host "Tache planifiee supprimee." -ForegroundColor Green

Get-NetFirewallRule -DisplayName "Gestion fournisseurs*" | Remove-NetFirewallRule
Write-Host "Regle de pare-feu supprimee." -ForegroundColor Green

$dataDir = [Environment]::GetEnvironmentVariable("DATA_DIR", "Machine")
foreach ($v in @("GESTION_LISTEN", "COOKIE_SECURE", "SESSION_HOURS", "ADMIN_PASSWORD")) {
    [Environment]::SetEnvironmentVariable($v, $null, "Machine")
}
Write-Host ""
Write-Host "SECRET_KEY et DATA_DIR ont ete conserves : sans eux," -ForegroundColor Yellow
Write-Host "une reinstallation ne retrouverait pas les sessions ni les donnees."
Write-Host ""
Write-Host "Vos donnees sont intactes dans : $dataDir" -ForegroundColor White
Read-Host "Entree pour fermer"
