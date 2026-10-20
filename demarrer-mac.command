#!/bin/bash
# Double-cliquez ce fichier pour lancer l'application sur votre Mac.
# Il prépare tout au premier lancement, puis ouvre le navigateur.

cd "$(dirname "$0")" || exit 1
clear
echo "Gestion des fournisseurs — démarrage local"
echo "=========================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo
  echo "Python 3 n'est pas installé."
  echo "Une fenêtre va proposer d'installer les outils de développement Apple."
  echo "Acceptez, patientez, puis relancez ce fichier."
  xcode-select --install 2>/dev/null
  read -r -p "Appuyez sur Entrée pour fermer."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Première installation, comptez une minute..."
  python3 -m venv .venv || { echo "Échec de la création de l'environnement."; read -r; exit 1; }
  ./.venv/bin/pip install --upgrade pip --quiet
  ./.venv/bin/pip install -r requirements.txt --quiet || { echo "Échec de l'installation."; read -r; exit 1; }
  echo "Installation terminée."
fi

export DATA_DIR="$(pwd)/data"
export HOST=127.0.0.1
export PORT=8000
export COOKIE_SECURE=0

if [ ! -f "data/gestion.db" ]; then
  echo
  echo "Première mise en route : notez le mot de passe affiché ci-dessous."
fi

echo
echo "L'application démarre sur http://127.0.0.1:8000"
echo "Laissez cette fenêtre ouverte. Pour arrêter : Ctrl-C."
echo

( sleep 3 && open "http://127.0.0.1:8000" ) &
./.venv/bin/python run.py
