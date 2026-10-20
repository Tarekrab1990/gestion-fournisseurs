"""Règles métier — un seul endroit pour les calculs de contrôle.

Le serveur est la référence : l'interface affiche ces valeurs mais ne les
recalcule jamais pour son compte.
"""

from datetime import date, timedelta

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin",
           "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def add_months(d, months):
    if not d:
        return None
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    day = min(d.day, [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def days_between(a, b):
    da, dbb = parse_date(a), parse_date(b)
    if not da or not dbb:
        return None
    return (dbb - da).days


def mois_de(iso):
    return str(iso)[:7] if iso else ""


def libelle_mois(ym):
    if not ym or len(ym) < 7:
        return "—"
    try:
        return f"{MOIS_FR[int(ym[5:7]) - 1]} {ym[:4]}"
    except (ValueError, IndexError):
        return ym


# --- C20 et dossier fiscal ---------------------------------------------------
def c20_expiration(supplier, validite_mois=12):
    if not supplier.get("c20_provided") or not supplier.get("c20_date"):
        return None
    exp = add_months(parse_date(supplier["c20_date"]), validite_mois)
    return exp.isoformat() if exp else None


def c20_alerte(supplier, validite_mois=12, preavis_jours=60, today=None):
    today = today or date.today()
    exp = c20_expiration(supplier, validite_mois)
    if not exp:
        return {"code": "absent", "label": "C20 absent", "tone": "danger",
                "expiration": None, "jours": None}
    jours = (parse_date(exp) - today).days
    if jours < 0:
        return {"code": "expire", "label": "C20 expiré", "tone": "danger",
                "expiration": exp, "jours": jours}
    if jours <= preavis_jours:
        return {"code": "bientot", "label": f"Expire dans {jours} j", "tone": "warn",
                "expiration": exp, "jours": jours}
    return {"code": "valide", "label": "C20 valide", "tone": "ok",
            "expiration": exp, "jours": jours}


def pieces_manquantes(supplier, validite_mois=12, preavis_jours=60, today=None):
    manque = []
    if not (supplier.get("nif") or "").strip():
        manque.append("NIF")
    if not (supplier.get("rc") or "").strip():
        manque.append("RC / agrément")
    if not (supplier.get("rib") or "").strip():
        manque.append("RIB")
    alerte = c20_alerte(supplier, validite_mois, preavis_jours, today)
    if alerte["code"] == "absent":
        manque.append("C20")
    elif alerte["code"] == "expire":
        manque.append("C20 à renouveler")
    return manque


def statut_dossier(supplier, validite_mois=12, preavis_jours=60, today=None):
    return "Complet" if not pieces_manquantes(supplier, validite_mois, preavis_jours, today) else "Incomplet"


def enrich_supplier(row, settings, today=None):
    s = dict(row)
    validite = int(settings.get("c20_validite_mois", 12))
    preavis = int(settings.get("c20_preavis_jours", 60))
    s["c20_provided"] = bool(s.get("c20_provided"))
    alerte = c20_alerte(s, validite, preavis, today)
    s["c20_expiration"] = alerte["expiration"]
    s["c20_alerte"] = alerte
    s["pieces_manquantes"] = pieces_manquantes(s, validite, preavis, today)
    s["statut_dossier"] = "Complet" if not s["pieces_manquantes"] else "Incomplet"
    return s


# --- Bons de commande --------------------------------------------------------
def statut_paiement(order):
    if order.get("debit_date"):
        return "Payé et débité"
    if order.get("payment_date"):
        return "Payé – en attente de débit"
    return "À payer"


def devis_requis(order, seuil):
    return float(order.get("amount_ttc") or 0) >= float(seuil)


def devis_etat(order, seuil):
    if not devis_requis(order, seuil):
        return {"code": "na", "label": "Sans objet", "tone": "neutral"}
    manque = []
    if not order.get("quote_done"):
        manque.append("à réaliser")
    elif not order.get("quote_date"):
        manque.append("date de création manquante")
    if order.get("quote_done") and not order.get("quote_signed"):
        manque.append("non signé")
    if not manque:
        if order.get("quote_approved_at"):
            return {"code": "ok", "label": "Validé", "tone": "ok"}
        return {"code": "attente", "label": "Complet, en attente de validation", "tone": "warn"}
    return {"code": "ko", "label": "Devis comparatif : " + ", ".join(manque), "tone": "danger"}


def enrich_order(row, settings, suppliers_by_name, today=None):
    o = dict(row)
    seuil = float(settings.get("seuil_devis", 350000))
    o["quote_done"] = bool(o.get("quote_done"))
    o["quote_signed"] = bool(o.get("quote_signed"))
    o["mois"] = mois_de(o.get("po_date"))
    o["mois_label"] = libelle_mois(o["mois"])
    o["statut_paiement"] = statut_paiement(o)
    o["devis_requis"] = devis_requis(o, seuil)
    o["devis_etat"] = devis_etat(o, seuil)
    o["delai_facture_paiement"] = days_between(o.get("invoice_date"), o.get("payment_date"))
    o["delai_paiement_debit"] = days_between(o.get("payment_date"), o.get("debit_date"))

    o["validation"] = etat_validation(o, settings)
    supplier = suppliers_by_name.get((o.get("supplier_name") or "").strip().lower())
    if supplier is None:
        o["dossier_fiscal"] = {"code": "inconnu", "label": "Fournisseur non référencé", "tone": "danger"}
    else:
        complet = supplier["statut_dossier"] == "Complet"
        o["dossier_fiscal"] = {
            "code": "ok" if complet else "ko",
            "label": "Dossier complet" if complet else "Dossier incomplet",
            "tone": "ok" if complet else "warn",
            "manque": supplier["pieces_manquantes"],
        }
    o["blocages"] = blocages(o, settings)
    return o


# --- circuit de validation des paiements -------------------------------------
ETATS_VALIDATION = {
    "brouillon": ("Règlement à demander", "neutral"),
    "demande":   ("En attente d'approbation", "warn"),
    "approuve":  ("Approuvé pour règlement", "ok"),
    "refuse":    ("Demande refusée", "danger"),
}


def etat_validation(order, settings):
    if str(settings.get("validation_paiement", "1")) not in ("1", "true", "oui"):
        return {"code": "na", "label": "Circuit désactivé", "tone": "neutral"}
    code = order.get("pay_state") or "brouillon"
    libelle, ton = ETATS_VALIDATION.get(code, ETATS_VALIDATION["brouillon"])
    return {"code": code, "label": libelle, "tone": ton}


def blocages(order, settings=None):
    """Motifs empêchant de demander la mise en paiement.

    Chaque contrôle peut être désactivé dans les paramètres : certaines
    organisations règlent avant réception de l'original, par exemple.
    """
    settings = settings or {}
    actif = lambda cle: str(settings.get(cle, "1")) in ("1", "true", "oui")
    motifs = []
    if actif("blocage_devis") and order["devis_etat"]["code"] in ("ko", "attente"):
        motifs.append(order["devis_etat"]["label"])
    if actif("blocage_dossier") and order["dossier_fiscal"]["code"] != "ok":
        motifs.append(order["dossier_fiscal"]["label"])
    if actif("blocage_facture") and (order.get("invoice_status") == "Facture non remise"
                                     or not order.get("invoice_number")):
        motifs.append("Facture originale non remise")
    return motifs


# --- Tableau de bord ---------------------------------------------------------
def worklist(suppliers, orders, settings, today=None):
    today = today or date.today()
    alerte_debit = int(settings.get("alerte_debit_jours", 15))
    seuil = float(settings.get("seuil_devis", 350000))
    items = []

    for s in suppliers:
        a = s["c20_alerte"]
        if a["code"] == "expire":
            items.append({"p": 1, "tone": "danger", "module": "fournisseurs",
                          "titre": f"{s['name']} — C20 expiré le {a['expiration']}",
                          "detail": "Aucun règlement ne devrait partir avant renouvellement du C20."})
        elif a["code"] == "absent":
            items.append({"p": 1, "tone": "danger", "module": "fournisseurs",
                          "titre": f"{s['name']} — C20 absent",
                          "detail": "Réclamer l'extrait de rôle apuré (C20) au fournisseur."})
        elif a["code"] == "bientot":
            items.append({"p": 3, "tone": "warn", "module": "fournisseurs",
                          "titre": f"{s['name']} — C20 expire dans {a['jours']} jours",
                          "detail": f"Expiration le {a['expiration']}. Lancer la relance maintenant."})
        autres = [m for m in s["pieces_manquantes"] if not m.startswith("C20")]
        if autres:
            items.append({"p": 2, "tone": "warn", "module": "fournisseurs",
                          "titre": f"{s['name']} — pièces manquantes",
                          "detail": "Manque : " + ", ".join(autres) + "."})

    for o in orders:
        de = o["devis_etat"]
        seuil_txt = f"{seuil:,.0f}".replace(",", " ")
        if de["code"] == "ko":
            items.append({"p": 1, "tone": "seuil", "module": "devis",
                          "titre": f"{o['po_number']} — {de['label'].lower()}",
                          "detail": f"Seuil de {seuil_txt} atteint. "
                                    f"{o['supplier_name']}, {o['description']}."})
        elif de["code"] == "attente":
            items.append({"p": 2, "tone": "seuil", "module": "devis",
                          "titre": f"{o['po_number']} — devis comparatif à valider",
                          "detail": f"Dossier complet, en attente de validation par la comptabilité."})
        if o["dossier_fiscal"]["code"] == "inconnu":
            items.append({"p": 2, "tone": "danger", "module": "fournisseurs",
                          "titre": f"{o['po_number']} — fournisseur non référencé",
                          "detail": f"{o['supplier_name']} n'existe pas dans les dossiers fiscaux."})
        if o["statut_paiement"] != "À payer" and (
                not o.get("invoice_number") or o.get("invoice_status") == "Facture non remise"):
            items.append({"p": 2, "tone": "warn", "module": "factures",
                          "titre": f"{o['po_number']} — payé sans facture originale",
                          "detail": f"Réclamer l'original à {o['supplier_name']}."})
        if o.get("validation", {}).get("code") == "demande":
            items.append({"p": 1, "tone": "warn", "module": "validation",
                          "titre": f"{o['po_number']} — règlement à approuver",
                          "detail": f"Demandé par {o.get('pay_requested_by') or '—'} "
                                    f"le {(o.get('pay_requested_at') or '')[:10]}, "
                                    f"{o['supplier_name']}."})
        if o.get("validation", {}).get("code") == "refuse":
            items.append({"p": 2, "tone": "danger", "module": "validation",
                          "titre": f"{o['po_number']} — demande de règlement refusée",
                          "detail": (o.get("pay_decision_note") or "Sans motif consigné.")})
        if o["statut_paiement"] == "Payé – en attente de débit":
            d = days_between(o.get("payment_date"), today.isoformat())
            if d is not None and d > alerte_debit:
                items.append({"p": 3, "tone": "warn", "module": "paiements",
                              "titre": f"{o['po_number']} — non débité depuis {d} jours",
                              "detail": f"Paiement du {o['payment_date']} par {o.get('payment_mode') or '—'}."})

    items.sort(key=lambda x: x["p"])
    return items
