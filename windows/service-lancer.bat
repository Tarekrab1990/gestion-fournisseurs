@echo off
rem Lance par la tache planifiee "GestionFournisseurs" au demarrage du PC.
rem Ne pas double-cliquer : utilisez demarrer-windows.bat pour un essai manuel.
setlocal
cd /d "%~dp0.."

if "%DATA_DIR%"=="" set "DATA_DIR=C:\ProgramData\GestionFournisseurs"
if "%GESTION_LISTEN%"=="" set "GESTION_LISTEN=0.0.0.0:8000"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

echo. >> "%DATA_DIR%\service.log"
echo ===== Demarrage %date% %time% ===== >> "%DATA_DIR%\service.log"

".venv\Scripts\waitress-serve.exe" --listen=%GESTION_LISTEN% --threads=8 ^
  --channel-timeout=120 wsgi:application >> "%DATA_DIR%\service.log" 2>&1

echo ===== Arret %date% %time% ===== >> "%DATA_DIR%\service.log"
endlocal
