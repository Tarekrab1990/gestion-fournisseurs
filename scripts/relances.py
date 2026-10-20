#!/usr/bin/env python3
"""Envoi automatique des relances — à programmer une fois par jour.

    python scripts/relances.py                 # envoie réellement
    python scripts/relances.py --simulation    # affiche sans envoyer
    python scripts/relances.py --sujet c20     # limite à un type de relance

Deux relances sont gérées :

  c20      fournisseurs dont le C20 est absent, expiré, ou expire dans moins de
           « relance_c20_jours » jours, et dont l'adresse de courriel est connue ;
  facture  bons de commande dont l'original de la facture n'est pas remis.

Un même sujet n'est pas relancé plus souvent que « relance_intervalle_jours »,
réglé dans Administration → Paramètres.

Cron (tous les jours à 8 h) :
    0 8 * * * cd /opt/gestion-fournisseurs && .venv/bin/python scripts/relances.py >> \\
              /var/log/gestion-relances.log 2>&1
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.database import query, execute, get_settings, audit, now
from app.rules import enrich_supplier, enrich_order
from app import mailer


def depuis(jours):
    return (datetime.now(timezone.utc) - timedelta(days=jours)).replace(microsecond=0).isoformat()


def relances_c20(settings, simulation):
    seuil_jours = int(settings.get("relance_c20_jours", 45))
    intervalle = int(settings.get("relance_intervalle_jours", 14))
    limite = depuis(intervalle)
    envoyes = ignores = echecs = 0

    for row in query("SELECT * FROM suppliers WHERE email <> ''"):
        f = enrich_supplier(row, settings)
        alerte = f["c20_alerte"]
        concerne = alerte["code"] in ("absent", "expire") or (
            alerte["code"] == "bientot" and (alerte["jours"] or 0) <= seuil_jours)
        if not concerne:
            continue
        if mailer.deja_relance("c20", "supplier", f["id"], limite):
            ignores += 1
            continue

        sujet, corps = mailer.modele_c20(f, settings)
        if simulation:
            print(f"  [simulation] {f['name']} <{f['email']}> : {sujet}")
            envoyes += 1
            continue
        try:
            mailer.envoyer(f["email"], sujet, corps, settings)
            mailer.journaliser("c20", "supplier", f["id"], f["email"], "envoye", par="automate")
            execute("UPDATE suppliers SET last_reminder = ? WHERE id = ?", (now()[:10], f["id"]))
            print(f"  envoyé : {f['name']} <{f['email']}> ({alerte['label']})")
            envoyes += 1
        except mailer.ErreurMessagerie as e:
            mailer.journaliser("c20", "supplier", f["id"], f["email"], "echec", str(e), par="automate")
            print(f"  ÉCHEC : {f['name']} — {e}", file=sys.stderr)
            echecs += 1
    return envoyes, ignores, echecs


def relances_facture(settings, simulation):
    intervalle = int(settings.get("relance_intervalle_jours", 14))
    limite = depuis(intervalle)
    adresses = {r["name"].strip().lower(): r["email"]
                for r in query("SELECT name, email FROM suppliers WHERE email <> ''")}
    suppliers = [enrich_supplier(r, settings) for r in query("SELECT * FROM suppliers")]
    index = {x["name"].strip().lower(): x for x in suppliers}
    envoyes = ignores = echecs = 0

    for row in query("SELECT * FROM purchase_orders"):
        o = enrich_order(row, settings, index)
        manquante = (not o["invoice_number"]) or o["invoice_status"] == "Facture non remise"
        if not manquante:
            continue
        adresse = adresses.get((o["supplier_name"] or "").strip().lower())
        if not adresse:
            continue
        if mailer.deja_relance("facture", "order", o["id"], limite):
            ignores += 1
            continue

        sujet, corps = mailer.modele_facture(o, settings)
        if simulation:
            print(f"  [simulation] {o['po_number']} -> <{adresse}> : {sujet}")
            envoyes += 1
            continue
        try:
            mailer.envoyer(adresse, sujet, corps, settings)
            mailer.journaliser("facture", "order", o["id"], adresse, "envoye", par="automate")
            print(f"  envoyé : {o['po_number']} -> <{adresse}>")
            envoyes += 1
        except mailer.ErreurMessagerie as e:
            mailer.journaliser("facture", "order", o["id"], adresse, "echec", str(e), par="automate")
            print(f"  ÉCHEC : {o['po_number']} — {e}", file=sys.stderr)
            echecs += 1
    return envoyes, ignores, echecs


def main():
    ap = argparse.ArgumentParser(description="Envoie les relances fournisseurs dues ce jour.")
    ap.add_argument("--simulation", action="store_true", help="n'envoie rien, affiche seulement")
    ap.add_argument("--sujet", choices=["c20", "facture", "tous"], default="tous")
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        settings = get_settings()
        if not args.simulation and not mailer.messagerie_prete(settings):
            sys.exit("La messagerie n'est pas configurée : renseignez le serveur SMTP et "
                     "l'adresse d'expédition dans Administration → Paramètres, et définissez "
                     "la variable d'environnement SMTP_PASSWORD si le serveur exige une "
                     "authentification.")

        total = [0, 0, 0]
        if args.sujet in ("c20", "tous"):
            print("Relances C20 :")
            for i, v in enumerate(relances_c20(settings, args.simulation)):
                total[i] += v
        if args.sujet in ("facture", "tous"):
            print("Relances factures :")
            for i, v in enumerate(relances_facture(settings, args.simulation)):
                total[i] += v

        print(f"\nBilan : {total[0]} envoyée(s), {total[1]} ignorée(s) (déjà relancées "
              f"récemment), {total[2]} en échec.")
        if not args.simulation and (total[0] or total[2]):
            audit("relances automatiques", "reminders", "",
                  f"{total[0]} envoyée(s), {total[2]} échec(s)", username="automate")
        sys.exit(1 if total[2] else 0)


if __name__ == "__main__":
    main()
