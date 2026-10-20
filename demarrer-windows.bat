@echo off
rem ===================================================================
rem  Gestion des fournisseurs - demarrage sur un PC Windows
rem  Double-cliquez ce fichier. La premiere fois, il installe ce qu'il
rem  faut (une minute), ensuite il demarre directement.
rem ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Gestion des fournisseurs

echo.
echo   Gestion des fournisseurs et des paiements
echo   =========================================
echo.

rem --- Python present ? ---------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY goto pas_de_python

rem Le raccourci du Microsoft Store n'est pas un vrai Python
%PY% -c "import sys; sys.exit(0)" >nul 2>&1
if errorlevel 1 goto pas_de_python

rem --- Environnement Python ------------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo   Premiere installation, patientez environ une minute...
  echo.
  %PY% -m venv .venv
  if errorlevel 1 goto echec_venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
  if errorlevel 1 goto echec_pip
  echo   Installation terminee.
  echo.
)

rem --- Reglages locaux ------------------------------------------------
set "DATA_DIR=%cd%\data"
set "HOST=127.0.0.1"
set "PORT=8000"
set "COOKIE_SECURE=0"
if not exist "data" mkdir "data"

if not exist "data\gestion.db" (
  echo   PREMIER DEMARRAGE : le mot de passe du compte "admin" va
  echo   s'afficher ci-dessous. Notez-le avant de fermer cette fenetre.
  echo.
)

echo   Adresse : http://127.0.0.1:8000
echo   Laissez cette fenetre ouverte. Pour arreter : Ctrl-C.
echo.

start "" /min cmd /c "timeout /t 4 >nul & start http://127.0.0.1:8000"
".venv\Scripts\python.exe" run.py
goto fin

rem --- Messages d'erreur ----------------------------------------------
:pas_de_python
echo   Python n'est pas installe sur ce poste.
echo.
echo   1. La page de telechargement va s'ouvrir.
echo   2. Prenez "Windows installer (64-bit)".
echo   3. IMPORTANT : cochez "Add python.exe to PATH" sur le premier ecran.
echo   4. Une fois l'installation finie, relancez ce fichier.
echo.
start "" https://www.python.org/downloads/windows/
pause
goto fin

:echec_venv
echo.
echo   Impossible de creer l'environnement Python.
echo   Verifiez que Python est bien installe : ouvrez une invite de
echo   commandes et tapez   python --version
pause
goto fin

:echec_pip
echo.
echo   L'installation des composants a echoue.
echo   Cause la plus frequente : pas d'acces reseau vers pypi.org.
echo   Voyez la section "Poste sans acces internet" de INSTALLATION.md.
pause

:fin
endlocal
