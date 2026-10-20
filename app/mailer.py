"""Envoi de courriels et modèles de relance.

Le mot de passe SMTP n'est jamais stocké en base : il est lu dans la variable
d'environnement SMTP_PASSWORD. Les autres réglages (hôte, port, expéditeur)
sont modifiables depuis l'interface par un administrateur.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate

from .database import query, execute, get_settings, now, audit
from .rules import libelle_mois


class ErreurMessagerie(Exception):
    pass


def configuration(settings=None):
    s = settings or get_settings()
    return {
        "hote": (s.get("smtp_hote") or "").strip(),
        "port": int(s.get("smtp_port") or 587),
        "utilisateur": (s.get("smtp_utilisateur") or "").strip(),
        "mot_de_passe": os.environ.get("SMTP_PASSWORD", ""),
        "tls": str(s.get("smtp_tls", "1")) in ("1", "true", "oui"),
        "expediteur": (s.get("smtp_expediteur") or "").strip(),
        "copie": (s.get("smtp_copie") or "").strip(),
        "organisation": s.get("org_name") or "Service achats",
    }


def messagerie_prete(settings=None):
    c = configuration(settings)
    return bool(c["hote"] and c["expediteur"])


def envoyer(destinataire, sujet, corps, settings=None, copie=None):
    """Envoie un message. Lève ErreurMessagerie en cas d'échec."""
    c = configuration(settings)
    if not c["hote"] or not c["expediteur"]:
        raise ErreurMessagerie("La messagerie n'est pas configurée "
                               "(Administration → Paramètres → Messagerie).")
    if not destinataire:
        raise ErreurMessagerie("Aucune adresse de destination.")

    msg = EmailMessage()
    msg["From"] = formataddr((c["organisation"], c["expediteur"]))
    msg["To"] = destinataire
    destinataires = [destinataire]
    copies = [x.strip() for x in (copie or c["copie"] or "").split(",") if x.strip()]
    if copies:
        msg["Cc"] = ", ".join(copies)
        destinataires += copies
    msg["Subject"] = sujet
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(corps)

    try:
        if c["port"] == 465:
            serveur = smtplib.SMTP_SSL(c["hote"], c["port"], timeout=20,
                                       context=ssl.create_default_context())
        else:
            serveur = smtplib.SMTP(c["hote"], c["port"], timeout=20)
            if c["tls"]:
                serveur.starttls(context=ssl.create_default_context())
        with serveur:
            if c["utilisateur"]:
                serveur.login(c["utilisateur"], c["mot_de_passe"])
            serveur.send_message(msg, to_addrs=destinataires)
    except smtplib.SMTPAuthenticationError:
        raise ErreurMessagerie("Le serveur SMTP a refusé les identifiants. "
                               "Vérifiez SMTP_PASSWORD et le compte utilisé.")
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        raise ErreurMessagerie(f"Envoi impossible : {e}")


def journaliser(sujet, entity, entity_id, destinataire, statut, erreur="", par="système"):
    execute("INSERT INTO reminders (sujet, entity, entity_id, destinataire, statut, erreur,"
            " envoye_par, envoye_le) VALUES (?,?,?,?,?,?,?,?)",
            (sujet, entity, entity_id, destinataire, statut, erreur[:400], par, now()))


def deja_relance(sujet, entity, entity_id, depuis_iso):
    r = query("SELECT COUNT(*) AS c FROM reminders WHERE sujet = ? AND entity = ?"
              " AND entity_id = ? AND statut = 'envoye' AND envoye_le >= ?",
              (sujet, entity, entity_id, depuis_iso), one=True)
    return int(r["c"]) > 0


# --- modèles -----------------------------------------------------------------
def modele_c20(fournisseur, settings):
    a = fournisseur["c20_alerte"]
    org = settings.get("org_name") or "Service achats"
    if a["code"] == "expire":
        sujet = f"Extrait de rôle apuré (C20) expiré — {fournisseur['name']}"
        ouverture = (f"Votre extrait de rôle apuré (C20) est arrivé à expiration le "
                     f"{a['expiration']}.")
    elif a["code"] == "absent":
        sujet = f"Extrait de rôle apuré (C20) manquant — {fournisseur['name']}"
        ouverture = "Nous ne disposons pas de votre extrait de rôle apuré (C20) en cours de validité."
    else:
        sujet = f"Extrait de rôle apuré (C20) à renouveler — {fournisseur['name']}"
        ouverture = (f"Votre extrait de rôle apuré (C20) arrive à expiration le "
                     f"{a['expiration']}, soit dans {a['jours']} jours.")

    manquantes = [m for m in fournisseur["pieces_manquantes"] if not m.startswith("C20")]
    bloc = ""
    if manquantes:
        bloc = ("\nNous vous remercions également de nous transmettre les pièces suivantes, "
                "absentes de votre dossier :\n" + "".join(f"  - {m}\n" for m in manquantes))

    corps = (
        f"Madame, Monsieur,\n\n{ouverture}\n\n"
        "Sans document à jour, nous ne sommes pas en mesure de procéder au règlement "
        "des factures en cours.\n"
        f"{bloc}\n"
        "Nous vous remercions de nous faire parvenir le document par retour de courriel.\n\n"
        f"Cordialement,\n{org}\n\n"
        "-- \nMessage envoyé automatiquement par l'application de suivi des fournisseurs."
    )
    return sujet, corps


def modele_facture(bon, settings):
    org = settings.get("org_name") or "Service achats"
    reference = bon["invoice_number"] or "(numéro non communiqué)"
    sujet = f"Facture originale attendue — bon de commande {bon['po_number']}"
    corps = (
        "Madame, Monsieur,\n\n"
        f"Nous n'avons pas reçu l'original de la facture {reference} se rapportant au bon de "
        f"commande {bon['po_number']} du {bon['po_date']} "
        f"({bon['description'] or 'prestation'}), d'un montant de "
        f"{int(float(bon['amount_ttc'])):,} {settings.get('devise', 'DZD')} TTC."
        .replace(",", " ") + "\n\n"
        "Le règlement ne peut être engagé sans facture originale. "
        "Nous vous remercions de nous la faire parvenir dans les meilleurs délais.\n\n"
        f"Cordialement,\n{org}\n\n"
        "-- \nMessage envoyé automatiquement par l'application de suivi des fournisseurs."
    )
    return sujet, corps


def modele_validation(bon, demandeur, settings):
    """Notification interne : une demande de règlement attend une décision."""
    org = settings.get("org_name") or "Service achats"
    sujet = f"Demande de règlement à approuver — {bon['po_number']}"
    corps = (
        "Bonjour,\n\n"
        f"{demandeur} demande la mise en paiement du bon de commande "
        f"{bon['po_number']} ({bon['supplier_name']}), "
        f"{int(float(bon['amount_ttc'])):,} {settings.get('devise', 'DZD')} TTC."
        .replace(",", " ") + "\n\n"
        "La demande est en attente dans le module « Validation paiements ».\n\n"
        f"{org}\n\n"
        "-- \nMessage envoyé automatiquement par l'application de suivi des fournisseurs."
    )
    return sujet, corps
