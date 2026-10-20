#!/usr/bin/env bash
# Sauvegarde à chaud de la base SQLite. À placer dans une tâche cron quotidienne :
#   0 20 * * * /opt/gestion-fournisseurs/scripts/sauvegarde.sh
set -euo pipefail

DATA_DIR="${DATA_DIR:-/var/lib/gestion-fournisseurs}"
DEST="${DEST:-$DATA_DIR/sauvegardes}"
RETENTION_JOURS="${RETENTION_JOURS:-30}"

mkdir -p "$DEST"
horodatage=$(date +%Y%m%d-%H%M%S)
cible="$DEST/gestion-$horodatage.db"

# .backup copie une base en cours d'utilisation sans risque d'incohérence.
sqlite3 "$DATA_DIR/gestion.db" ".backup '$cible'"
gzip -f "$cible"
find "$DEST" -name 'gestion-*.db.gz' -mtime "+$RETENTION_JOURS" -delete

echo "Sauvegarde écrite : $cible.gz"
