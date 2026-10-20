#!/usr/bin/env python3
"""Recopie une base SQLite existante vers PostgreSQL.

    python scripts/migrer_postgres.py \\
        --source /var/lib/gestion-fournisseurs/gestion.db \\
        --cible "postgresql://gestion:motdepasse@127.0.0.1:5432/gestion"

Le schéma est créé dans la base cible si nécessaire, puis les tables sont
copiées dans l'ordre des dépendances. La base source n'est jamais modifiée.
Arrêtez l'application avant de lancer la migration.
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TABLES = [
    "roles", "role_permissions", "users", "departments", "suppliers",
    "purchase_orders", "attachments", "reminders", "settings", "audit_log",
]
SEQUENCES = {
    "roles": "roles_id_seq", "users": "users_id_seq", "departments": "departments_id_seq",
    "suppliers": "suppliers_id_seq", "purchase_orders": "purchase_orders_id_seq",
    "attachments": "attachments_id_seq", "reminders": "reminders_id_seq",
    "audit_log": "audit_log_id_seq",
}


def main():
    ap = argparse.ArgumentParser(description="Migre la base SQLite vers PostgreSQL.")
    ap.add_argument("--source", required=True, help="fichier .db SQLite")
    ap.add_argument("--cible", required=True, help="URL PostgreSQL")
    ap.add_argument("--vider", action="store_true",
                    help="vide les tables de destination avant la copie")
    args = ap.parse_args()

    if not os.path.exists(args.source):
        sys.exit(f"Base source introuvable : {args.source}")
    try:
        import psycopg
    except ImportError:
        sys.exit("psycopg est requis : pip install \"psycopg[binary]\"")

    # crée le schéma côté PostgreSQL via l'application elle-même
    os.environ["DATABASE_URL"] = args.cible
    from app import create_app
    create_app()
    print("Schéma PostgreSQL prêt.")

    src = sqlite3.connect(args.source)
    src.row_factory = sqlite3.Row

    with psycopg.connect(args.cible) as dst:
        with dst.cursor() as cur:
            if args.vider:
                cur.execute("TRUNCATE " + ", ".join(reversed(TABLES)) + " RESTART IDENTITY CASCADE")
                print("Tables de destination vidées.")

            total = 0
            for table in TABLES:
                try:
                    lignes = src.execute(f"SELECT * FROM {table}").fetchall()
                except sqlite3.OperationalError:
                    print(f"  {table} : absente de la source, ignorée")
                    continue
                if not lignes:
                    print(f"  {table} : vide")
                    continue
                colonnes = lignes[0].keys()
                marques = ",".join(["%s"] * len(colonnes))
                sql = (f"INSERT INTO {table} ({','.join(colonnes)}) VALUES ({marques})"
                       " ON CONFLICT DO NOTHING")
                cur.executemany(sql, [tuple(l) for l in lignes])
                print(f"  {table} : {len(lignes)} ligne(s)")
                total += len(lignes)

            # remet les séquences au-delà des identifiants recopiés
            for table, sequence in SEQUENCES.items():
                cur.execute(
                    f"SELECT setval('{sequence}', COALESCE((SELECT MAX(id) FROM {table}), 1), true)")
        dst.commit()

    src.close()
    print(f"\nMigration terminée : {total} ligne(s) copiée(s).")
    print("Ajoutez DATABASE_URL au fichier d'environnement, puis redémarrez le service.")
    print("Les pièces jointes restent des fichiers dans DATA_DIR : rien à migrer.")


if __name__ == "__main__":
    main()
