"""API métier : fournisseurs, bons de commande, factures, paiements, devis."""

import csv
import io
from datetime import date

from flask import Blueprint, request, jsonify, Response

from .database import query, execute, get_db, get_settings, audit, now, param_bool
from .rules import (enrich_supplier, enrich_order, worklist, libelle_mois,
                    mois_de, blocages, etat_validation)
from .attachments import compter_par_entite
from . import mailer
from .security import current_user, user_permissions, require, login_required, check_csrf

bp = Blueprint("api", __name__, url_prefix="/api")

# Champs d'un bon de commande, par groupe de permission
GROUPES = {
    "bons.edit":     ["po_number", "po_date", "department", "supplier_name", "description",
                      "amount_ttc", "note"],
    "factures.edit": ["invoice_number", "invoice_date", "invoice_status"],
    "paiements.edit": ["payment_mode", "cheque_number", "transfer_number",
                       "payment_date", "debit_date"],
    "devis.edit":    ["quote_done", "quote_date", "quote_signed"],
}
CHAMP_GROUPE = {champ: perm for perm, champs in GROUPES.items() for champ in champs}

ETATS_FACTURE = ["", "Facture remise", "Facture non remise"]
MODES = ["", "Chèque", "Virement"]


def s(v):
    return ("" if v is None else str(v)).strip()


def as_bool(v):
    return 1 if v in (True, 1, "1", "true", "True", "oui", "Oui") else 0


def valid_date(v, champ, errors, obligatoire=False):
    v = s(v)
    if not v:
        if obligatoire:
            errors.append(f"{champ} est obligatoire.")
        return ""
    try:
        date.fromisoformat(v[:10])
        return v[:10]
    except ValueError:
        errors.append(f"{champ} : date invalide (format attendu AAAA-MM-JJ).")
        return ""


# --- Lecture globale ---------------------------------------------------------
def charger(perms):
    settings = get_settings()
    suppliers = [enrich_supplier(r, settings) for r in
                 query("SELECT * FROM suppliers ORDER BY lower(name)")]
    index = {sup["name"].strip().lower(): sup for sup in suppliers}
    orders = [enrich_order(r, settings, index) for r in
              query("SELECT * FROM purchase_orders ORDER BY po_date DESC, id DESC")]
    return settings, suppliers, orders


@bp.get("/data")
@login_required
def data():
    user = current_user()
    perms = user_permissions(user)
    settings, suppliers, orders = charger(perms)

    peut_voir_bons = bool(perms & {"bons.view", "factures.view", "paiements.view", "devis.view"})
    if "pieces.view" in perms:
        pf, pb = compter_par_entite("supplier"), compter_par_entite("order")
        for x in suppliers:
            x["nb_pieces"] = pf.get(int(x["id"]), 0)
        for o in orders:
            o["nb_pieces"] = pb.get(int(o["id"]), 0)
    out = {
        "parametres": settings,
        "departements": [r["name"] for r in
                         query("SELECT name FROM departments WHERE is_active = 1 ORDER BY name")],
        "etats_facture": [e for e in ETATS_FACTURE if e],
        "modes_paiement": [m for m in MODES if m],
        "fournisseurs": suppliers if "fournisseurs.view" in perms else [],
        "bons": orders if peut_voir_bons else [],
    }
    if "tableau.view" in perms:
        out["travail"] = worklist(suppliers, orders, settings)
        total = sum(float(o["amount_ttc"] or 0) for o in orders)
        a_payer = [o for o in orders if o["statut_paiement"] == "À payer"]
        attente = [o for o in orders if o["statut_paiement"] == "Payé – en attente de débit"]
        out["indicateurs"] = {
            "nb_bons": len(orders),
            "engage": total,
            "nb_a_payer": len(a_payer),
            "montant_a_payer": sum(float(o["amount_ttc"] or 0) for o in a_payer),
            "nb_attente_debit": len(attente),
            "montant_attente_debit": sum(float(o["amount_ttc"] or 0) for o in attente),
            "dossiers_incomplets": sum(1 for x in suppliers if x["statut_dossier"] != "Complet"),
            "devis_non_conformes": sum(1 for o in orders if o["devis_etat"]["code"] in ("ko", "attente")),
            "factures_manquantes": sum(1 for o in orders if not o["invoice_number"]
                                       or o["invoice_status"] == "Facture non remise"),
            "demandes_en_attente": sum(1 for o in orders if o["validation"]["code"] == "demande"),
        }
        par_mois = {}
        for o in orders:
            k = o["mois"] or "—"
            e = par_mois.setdefault(k, {"mois": k, "label": libelle_mois(k), "nb": 0,
                                        "ttc": 0.0, "regle": 0.0, "reste": 0.0})
            e["nb"] += 1
            montant = float(o["amount_ttc"] or 0)
            e["ttc"] += montant
            if o["statut_paiement"] == "À payer":
                e["reste"] += montant
            else:
                e["regle"] += montant
        out["par_mois"] = sorted(par_mois.values(), key=lambda x: x["mois"], reverse=True)
    return jsonify(out)


# --- Fournisseurs ------------------------------------------------------------
def supplier_payload(data, errors):
    nom = s(data.get("name"))
    if not nom:
        errors.append("Le nom du fournisseur est obligatoire.")
    fourni = as_bool(data.get("c20_provided"))
    c20 = valid_date(data.get("c20_date"), "Date du C20", errors)
    if fourni and not c20:
        errors.append("Indiquez la date du C20 pour calculer son expiration.")
    return {
        "name": nom,
        "department": s(data.get("department")),
        "nif": s(data.get("nif")),
        "rc": s(data.get("rc")),
        "rib": s(data.get("rib")),
        "c20_provided": fourni,
        "c20_date": c20 if fourni else "",
        "contact": s(data.get("contact")),
        "email": s(data.get("email")),
        "last_reminder": valid_date(data.get("last_reminder"), "Date de relance", errors),
        "note": s(data.get("note")),
    }


@bp.post("/suppliers")
@require("fournisseurs.edit")
def create_supplier():
    errors = []
    p = supplier_payload(request.get_json(silent=True) or {}, errors)
    if errors:
        return jsonify({"error": " ".join(errors)}), 400
    if query("SELECT id FROM suppliers WHERE name = ?", (p["name"],), one=True):
        return jsonify({"error": "Ce fournisseur existe déjà dans les dossiers fiscaux."}), 409
    user = current_user()
    sid = execute(
        "INSERT INTO suppliers (name, department, nif, rc, rib, c20_provided, c20_date,"
        " contact, email, last_reminder, note, created_at, updated_at, updated_by)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (p["name"], p["department"], p["nif"], p["rc"], p["rib"], p["c20_provided"],
         p["c20_date"], p["contact"], p["email"], p["last_reminder"], p["note"],
         now(), now(), user["username"]),
    )
    audit("création fournisseur", "supplier", sid, p["name"])
    return jsonify({"id": sid}), 201


@bp.put("/suppliers/<int:sid>")
@require("fournisseurs.edit")
def update_supplier(sid):
    ancien = query("SELECT * FROM suppliers WHERE id = ?", (sid,), one=True)
    if not ancien:
        return jsonify({"error": "Fournisseur introuvable."}), 404
    errors = []
    p = supplier_payload(request.get_json(silent=True) or {}, errors)
    if errors:
        return jsonify({"error": " ".join(errors)}), 400
    doublon = query("SELECT id FROM suppliers WHERE name = ? AND id <> ?", (p["name"], sid), one=True)
    if doublon:
        return jsonify({"error": "Un autre fournisseur porte déjà ce nom."}), 409
    user = current_user()
    execute(
        "UPDATE suppliers SET name=?, department=?, nif=?, rc=?, rib=?, c20_provided=?,"
        " c20_date=?, contact=?, email=?, last_reminder=?, note=?, updated_at=?,"
        " updated_by=? WHERE id=?",
        (p["name"], p["department"], p["nif"], p["rc"], p["rib"], p["c20_provided"],
         p["c20_date"], p["contact"], p["email"], p["last_reminder"], p["note"],
         now(), user["username"], sid),
    )
    if ancien["name"] != p["name"]:
        execute("UPDATE purchase_orders SET supplier_name = ? WHERE supplier_name = ?",
                (p["name"], ancien["name"]))
    modifs = [k for k in p if s(ancien[k]) != s(p[k])]
    audit("modification fournisseur", "supplier", sid, f"{p['name']} — {', '.join(modifs) or 'aucun changement'}")
    return jsonify({"ok": True})


@bp.delete("/suppliers/<int:sid>")
@require("fournisseurs.delete")
def delete_supplier(sid):
    row = query("SELECT * FROM suppliers WHERE id = ?", (sid,), one=True)
    if not row:
        return jsonify({"error": "Fournisseur introuvable."}), 404
    lies = query("SELECT COUNT(*) c FROM purchase_orders WHERE supplier_name = ?",
                 (row["name"],), one=True)["c"]
    execute("DELETE FROM suppliers WHERE id = ?", (sid,))
    audit("suppression fournisseur", "supplier", sid, f"{row['name']} — {lies} bon(s) désormais non référencé(s)")
    return jsonify({"ok": True, "bons_orphelins": lies})


# --- Bons de commande --------------------------------------------------------
def order_payload(data, errors, existant=None):
    p = {}
    p["po_number"] = s(data.get("po_number"))
    if not p["po_number"]:
        errors.append("Le numéro du bon de commande est obligatoire.")
    p["po_date"] = valid_date(data.get("po_date"), "Date du bon de commande", errors, obligatoire=True)
    p["department"] = s(data.get("department"))
    p["supplier_name"] = s(data.get("supplier_name"))
    if not p["supplier_name"]:
        errors.append("Indiquez le fournisseur.")
    p["description"] = s(data.get("description"))
    try:
        p["amount_ttc"] = float(data.get("amount_ttc") or 0)
    except (TypeError, ValueError):
        p["amount_ttc"] = 0.0
        errors.append("Montant TTC invalide.")
    if p["amount_ttc"] <= 0:
        errors.append("Le montant TTC doit être supérieur à zéro.")
    p["note"] = s(data.get("note"))

    p["invoice_number"] = s(data.get("invoice_number"))
    p["invoice_date"] = valid_date(data.get("invoice_date"), "Date de facture", errors)
    p["invoice_status"] = s(data.get("invoice_status"))
    if p["invoice_status"] not in ETATS_FACTURE:
        errors.append("État de facture inconnu.")

    p["payment_mode"] = s(data.get("payment_mode"))
    if p["payment_mode"] not in MODES:
        errors.append("Mode de paiement inconnu.")
    p["cheque_number"] = s(data.get("cheque_number")) if p["payment_mode"] != "Virement" else ""
    p["transfer_number"] = s(data.get("transfer_number")) if p["payment_mode"] != "Chèque" else ""
    p["payment_date"] = valid_date(data.get("payment_date"), "Date de paiement", errors)
    p["debit_date"] = valid_date(data.get("debit_date"), "Date de débit", errors)
    if p["debit_date"] and not p["payment_date"]:
        errors.append("Une date de débit suppose une date de paiement.")
    if p["payment_date"] and p["debit_date"] and p["debit_date"] < p["payment_date"]:
        errors.append("La date de débit ne peut pas précéder la date de paiement.")

    p["quote_done"] = as_bool(data.get("quote_done"))
    p["quote_date"] = valid_date(data.get("quote_date"), "Date du devis comparatif", errors)
    p["quote_signed"] = as_bool(data.get("quote_signed"))

    seuil = float(get_settings().get("seuil_devis", 350000))
    if p["amount_ttc"] < seuil:
        p["quote_done"], p["quote_date"], p["quote_signed"] = 0, "", 0
    return p


def groupes_modifies(ancien, nouveau):
    """Permissions nécessaires compte tenu des champs réellement modifiés."""
    besoins = set()
    for champ, perm in CHAMP_GROUPE.items():
        avant = ancien[champ] if ancien is not None else None
        apres = nouveau.get(champ)
        if champ == "amount_ttc":
            if float(avant or 0) != float(apres or 0):
                besoins.add(perm)
        elif champ in ("quote_done", "quote_signed"):
            if as_bool(avant) != as_bool(apres):
                besoins.add(perm)
        elif s(avant) != s(apres):
            besoins.add(perm)
    return besoins


@bp.post("/orders")
@require("bons.edit")
def create_order():
    errors = []
    p = order_payload(request.get_json(silent=True) or {}, errors)
    if errors:
        return jsonify({"error": " ".join(errors)}), 400
    if query("SELECT id FROM purchase_orders WHERE po_number = ?", (p["po_number"],), one=True):
        return jsonify({"error": "Ce numéro de bon de commande est déjà enregistré."}), 409
    perms = user_permissions(current_user())
    besoins = groupes_modifies(None, p)
    manquant = besoins - perms - {"bons.edit"}
    if manquant:
        return jsonify({"error": "Votre rôle ne permet pas de renseigner "
                                 + ", ".join(sorted(manquant)) + " à la création.",
                        "missing": sorted(manquant)}), 403
    user = current_user()
    champs = list(p.keys())
    oid = execute(
        f"INSERT INTO purchase_orders ({','.join(champs)}, created_at, updated_at, updated_by)"
        f" VALUES ({','.join('?' * len(champs))},?,?,?)",
        tuple(p[c] for c in champs) + (now(), now(), user["username"]),
    )
    audit("création bon de commande", "order", oid,
          f"{p['po_number']} — {p['supplier_name']} — {p['amount_ttc']:.0f}")
    return jsonify({"id": oid}), 201


@bp.put("/orders/<int:oid>")
@login_required
def update_order(oid):
    ancien = query("SELECT * FROM purchase_orders WHERE id = ?", (oid,), one=True)
    if not ancien:
        return jsonify({"error": "Bon de commande introuvable."}), 404
    errors = []
    p = order_payload(request.get_json(silent=True) or {}, errors, ancien)
    if errors:
        return jsonify({"error": " ".join(errors)}), 400

    perms = user_permissions(current_user())
    besoins = groupes_modifies(ancien, p)
    if not besoins:
        return jsonify({"ok": True, "inchange": True})
    manquant = besoins - perms
    if manquant:
        libelles = {"bons.edit": "le bon de commande", "factures.edit": "la facture",
                    "paiements.edit": "le paiement", "devis.edit": "le devis comparatif"}
        return jsonify({"error": "Votre rôle ne permet pas de modifier "
                                 + ", ".join(libelles.get(m, m) for m in sorted(manquant)) + ".",
                        "missing": sorted(manquant)}), 403

    doublon = query("SELECT id FROM purchase_orders WHERE po_number = ? AND id <> ?",
                    (p["po_number"], oid), one=True)
    if doublon:
        return jsonify({"error": "Ce numéro de bon de commande est déjà enregistré."}), 409

    reglages = get_settings()
    if (param_bool(reglages, "validation_paiement") and "paiements.edit" in besoins
            and (p["payment_date"] or p["debit_date"])
            and (ancien.get("pay_state") or "brouillon") != "approuve"):
        return jsonify({"error": "Le circuit de validation est actif : ce bon doit d'abord être "
                                 "approuvé dans le module « Validation paiements » avant toute "
                                 "saisie de règlement."}), 409

    # une modification du devis annule une validation antérieure
    if "devis.edit" in besoins and ancien["quote_approved_at"]:
        p["quote_approved_at"] = ""
        p["quote_approved_by"] = ""

    user = current_user()
    champs = list(p.keys())
    execute(
        f"UPDATE purchase_orders SET {','.join(c + '=?' for c in champs)},"
        " updated_at=?, updated_by=? WHERE id=?",
        tuple(p[c] for c in champs) + (now(), user["username"], oid),
    )
    audit("modification bon de commande", "order", oid,
          f"{p['po_number']} — {', '.join(sorted(besoins))}")
    return jsonify({"ok": True})


@bp.delete("/orders/<int:oid>")
@require("bons.delete")
def delete_order(oid):
    row = query("SELECT * FROM purchase_orders WHERE id = ?", (oid,), one=True)
    if not row:
        return jsonify({"error": "Bon de commande introuvable."}), 404
    execute("DELETE FROM purchase_orders WHERE id = ?", (oid,))
    audit("suppression bon de commande", "order", oid, row["po_number"])
    return jsonify({"ok": True})


@bp.patch("/orders/<int:oid>/devis")
@require("devis.edit")
def patch_quote(oid):
    row = query("SELECT * FROM purchase_orders WHERE id = ?", (oid,), one=True)
    if not row:
        return jsonify({"error": "Bon de commande introuvable."}), 404
    seuil = float(get_settings().get("seuil_devis", 350000))
    if float(row["amount_ttc"] or 0) < seuil:
        return jsonify({"error": "Ce bon de commande n'atteint pas le seuil du devis comparatif."}), 400
    data = request.get_json(silent=True) or {}
    errors = []
    done = as_bool(data.get("quote_done", row["quote_done"]))
    qdate = valid_date(data.get("quote_date", row["quote_date"]), "Date du devis comparatif", errors)
    signed = as_bool(data.get("quote_signed", row["quote_signed"]))
    if errors:
        return jsonify({"error": " ".join(errors)}), 400
    execute("UPDATE purchase_orders SET quote_done=?, quote_date=?, quote_signed=?,"
            " quote_approved_at='', quote_approved_by='', updated_at=?, updated_by=? WHERE id=?",
            (done, qdate, signed, now(), current_user()["username"], oid))
    audit("mise à jour devis comparatif", "order", oid,
          f"{row['po_number']} — réalisé={'oui' if done else 'non'},"
          f" date={qdate or '—'}, signé={'oui' if signed else 'non'}")
    return jsonify({"ok": True})


@bp.post("/orders/<int:oid>/devis/valider")
@require("devis.approve")
def approve_quote(oid):
    row = query("SELECT * FROM purchase_orders WHERE id = ?", (oid,), one=True)
    if not row:
        return jsonify({"error": "Bon de commande introuvable."}), 404
    if not (row["quote_done"] and row["quote_date"] and row["quote_signed"]):
        return jsonify({"error": "Le dossier de devis comparatif est incomplet : "
                                 "il doit être réalisé, daté et signé."}), 400
    user = current_user()
    execute("UPDATE purchase_orders SET quote_approved_by=?, quote_approved_at=?,"
            " updated_at=?, updated_by=? WHERE id=?",
            (user["full_name"] or user["username"], now(), now(), user["username"], oid))
    audit("validation devis comparatif", "order", oid, row["po_number"])
    return jsonify({"ok": True})


# --- Exports -----------------------------------------------------------------
@bp.get("/export/<kind>.csv")
@require("export.csv")
def export(kind):
    settings, suppliers, orders = charger(user_permissions(current_user()))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    if kind == "fournisseurs":
        w.writerow(["Fournisseur", "Département", "NIF", "RC / agrément", "RIB",
                    "Date du C20", "Expiration C20", "Alerte C20", "Statut dossier",
                    "Pièces manquantes", "Contact", "Courriel", "Dernière relance", "Remarque"])
        for x in suppliers:
            w.writerow([x["name"], x["department"], x["nif"], x["rc"], x["rib"],
                        x["c20_date"], x["c20_expiration"] or "", x["c20_alerte"]["label"],
                        x["statut_dossier"], " / ".join(x["pieces_manquantes"]),
                        x["contact"], x.get("email", ""), x["last_reminder"], x["note"]])
    elif kind in ("bons", "factures", "paiements", "devis"):
        lignes = [o for o in orders if o["devis_requis"]] if kind == "devis" else orders
        w.writerow(["Mois", "Date BC", "N° BC", "Département", "Fournisseur", "Prestation",
                    "Montant TTC", "N° facture", "Date facture", "État facture",
                    "Mode de paiement", "N° chèque", "N° ordre de virement",
                    "Date de paiement", "Date de débit", "Statut paiement",
                    "Délai facture→paiement", "Délai paiement→débit",
                    "Devis requis", "Devis réalisé", "Date du devis", "Devis signé",
                    "Contrôle devis", "Validé par", "Dossier fiscal",
                    "Circuit de validation", "Demandé par", "Demandé le",
                    "Décidé par", "Décidé le", "Observation"])
        for o in lignes:
            w.writerow([o["mois_label"], o["po_date"], o["po_number"], o["department"],
                        o["supplier_name"], o["description"], f"{float(o['amount_ttc']):.0f}",
                        o["invoice_number"], o["invoice_date"], o["invoice_status"],
                        o["payment_mode"], o["cheque_number"], o["transfer_number"],
                        o["payment_date"], o["debit_date"], o["statut_paiement"],
                        o["delai_facture_paiement"] if o["delai_facture_paiement"] is not None else "",
                        o["delai_paiement_debit"] if o["delai_paiement_debit"] is not None else "",
                        "Oui" if o["devis_requis"] else "Non",
                        "Oui" if o["quote_done"] else "Non", o["quote_date"],
                        "Oui" if o["quote_signed"] else "Non", o["devis_etat"]["label"],
                        o["quote_approved_by"], o["dossier_fiscal"]["label"],
                        o["validation"]["label"], o["pay_requested_by"],
                        (o["pay_requested_at"] or "")[:10], o["pay_decided_by"],
                        (o["pay_decided_at"] or "")[:10], o["pay_decision_note"]])
    else:
        return jsonify({"error": "Export inconnu."}), 404

    audit("export CSV", "export", kind)
    csv_text = "\ufeff" + buf.getvalue()
    return Response(csv_text, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'})


# --- circuit de validation des règlements ------------------------------------
def _bon_enrichi(oid):
    settings = get_settings()
    row = query("SELECT * FROM purchase_orders WHERE id = ?", (oid,), one=True)
    if not row:
        return None, settings
    suppliers = [enrich_supplier(r, settings) for r in query("SELECT * FROM suppliers")]
    index = {x["name"].strip().lower(): x for x in suppliers}
    return enrich_order(row, settings, index), settings


@bp.post("/orders/<int:oid>/paiement/demander")
@require("paiements.request")
def demander_reglement(oid):
    bon, settings = _bon_enrichi(oid)
    if not bon:
        return jsonify({"error": "Bon de commande introuvable."}), 404
    if not param_bool(settings, "validation_paiement"):
        return jsonify({"error": "Le circuit de validation est désactivé dans les paramètres."}), 400
    if bon["pay_state"] == "demande":
        return jsonify({"error": "Une demande est déjà en attente sur ce bon."}), 409
    if bon["pay_state"] == "approuve":
        return jsonify({"error": "Ce bon est déjà approuvé pour règlement."}), 409
    if bon["statut_paiement"] != "À payer":
        return jsonify({"error": "Ce bon est déjà réglé."}), 400

    motifs = bon["blocages"]
    if motifs:
        return jsonify({"error": "Demande impossible : " + " ; ".join(motifs) + ".",
                        "blocages": motifs}), 409

    user = current_user()
    demandeur = user["full_name"] or user["username"]
    execute("UPDATE purchase_orders SET pay_state='demande', pay_requested_by=?,"
            " pay_requested_at=?, pay_decided_by='', pay_decided_at='', pay_decision_note='',"
            " updated_at=?, updated_by=? WHERE id=?",
            (demandeur, now(), now(), user["username"], oid))
    audit("demande de règlement", "order", oid, f"{bon['po_number']} — {bon['supplier_name']}")

    notifies = 0
    if mailer.messagerie_prete(settings):
        sujet, corps = mailer.modele_validation(bon, demandeur, settings)
        destinataires = query(
            "SELECT DISTINCT u.email FROM users u JOIN role_permissions rp ON rp.role_id = u.role_id"
            " WHERE rp.permission = 'paiements.approve' AND u.is_active = 1 AND u.email <> ''")
        for d in destinataires:
            try:
                mailer.envoyer(d["email"], sujet, corps, settings)
                mailer.journaliser("validation", "order", oid, d["email"], "envoye",
                                   par=user["username"])
                notifies += 1
            except mailer.ErreurMessagerie as e:
                mailer.journaliser("validation", "order", oid, d["email"], "echec", str(e),
                                   par=user["username"])
    return jsonify({"ok": True, "approbateurs_notifies": notifies})


@bp.post("/orders/<int:oid>/paiement/decider")
@require("paiements.approve")
def decider_reglement(oid):
    bon, settings = _bon_enrichi(oid)
    if not bon:
        return jsonify({"error": "Bon de commande introuvable."}), 404
    data = request.get_json(silent=True) or {}
    decision = s(data.get("decision"))
    motif = s(data.get("motif"))[:400]
    if decision not in ("approuve", "refuse"):
        return jsonify({"error": "Décision inconnue."}), 400
    if bon["pay_state"] != "demande":
        return jsonify({"error": "Aucune demande en attente sur ce bon."}), 409
    if decision == "refuse" and not motif:
        return jsonify({"error": "Un refus doit être motivé."}), 400
    if decision == "approuve" and bon["blocages"]:
        return jsonify({"error": "Approbation impossible : " + " ; ".join(bon["blocages"]) + "."}), 409

    user = current_user()
    execute("UPDATE purchase_orders SET pay_state=?, pay_decided_by=?, pay_decided_at=?,"
            " pay_decision_note=?, updated_at=?, updated_by=? WHERE id=?",
            (decision, user["full_name"] or user["username"], now(), motif, now(),
             user["username"], oid))
    audit("approbation de règlement" if decision == "approuve" else "refus de règlement",
          "order", oid, f"{bon['po_number']} — {motif or 'sans observation'}")
    return jsonify({"ok": True})


@bp.post("/orders/<int:oid>/paiement/annuler")
@require("paiements.request")
def annuler_demande(oid):
    bon, _ = _bon_enrichi(oid)
    if not bon:
        return jsonify({"error": "Bon de commande introuvable."}), 404
    if bon["pay_state"] not in ("demande", "refuse"):
        return jsonify({"error": "Seule une demande en attente ou refusée peut être retirée."}), 409
    user = current_user()
    execute("UPDATE purchase_orders SET pay_state='brouillon', pay_requested_by='',"
            " pay_requested_at='', pay_decided_by='', pay_decided_at='', pay_decision_note='',"
            " updated_at=?, updated_by=? WHERE id=?", (now(), user["username"], oid))
    audit("retrait de la demande de règlement", "order", oid, bon["po_number"])
    return jsonify({"ok": True})


# --- relances par courriel ---------------------------------------------------
@bp.post("/relances/fournisseur/<int:sid>")
@require("relances.send")
def relancer_fournisseur(sid):
    settings = get_settings()
    row = query("SELECT * FROM suppliers WHERE id = ?", (sid,), one=True)
    if not row:
        return jsonify({"error": "Fournisseur introuvable."}), 404
    fournisseur = enrich_supplier(row, settings)
    if not fournisseur.get("email"):
        return jsonify({"error": "Ce fournisseur n'a pas d'adresse de courriel enregistrée."}), 400
    if fournisseur["statut_dossier"] == "Complet":
        return jsonify({"error": "Le dossier de ce fournisseur est complet : rien à relancer."}), 400

    sujet, corps = mailer.modele_c20(fournisseur, settings)
    user = current_user()
    try:
        mailer.envoyer(fournisseur["email"], sujet, corps, settings)
    except mailer.ErreurMessagerie as e:
        mailer.journaliser("c20", "supplier", sid, fournisseur["email"], "echec", str(e),
                           par=user["username"])
        return jsonify({"error": str(e)}), 502
    mailer.journaliser("c20", "supplier", sid, fournisseur["email"], "envoye",
                       par=user["username"])
    execute("UPDATE suppliers SET last_reminder = ? WHERE id = ?",
            (now()[:10], sid))
    audit("relance fournisseur", "supplier", sid, f"{fournisseur['name']} -> {fournisseur['email']}")
    return jsonify({"ok": True, "destinataire": fournisseur["email"]})


@bp.post("/relances/facture/<int:oid>")
@require("relances.send")
def relancer_facture(oid):
    bon, settings = _bon_enrichi(oid)
    if not bon:
        return jsonify({"error": "Bon de commande introuvable."}), 404
    fournisseur = query("SELECT * FROM suppliers WHERE lower(name) = lower(?)",
                        (bon["supplier_name"],), one=True)
    adresse = (fournisseur or {}).get("email", "")
    if not adresse:
        return jsonify({"error": "Aucune adresse de courriel pour ce fournisseur."}), 400
    if bon["invoice_status"] == "Facture remise" and bon["invoice_number"]:
        return jsonify({"error": "L'original de cette facture est déjà enregistré comme remis."}), 400

    sujet, corps = mailer.modele_facture(bon, settings)
    user = current_user()
    try:
        mailer.envoyer(adresse, sujet, corps, settings)
    except mailer.ErreurMessagerie as e:
        mailer.journaliser("facture", "order", oid, adresse, "echec", str(e), par=user["username"])
        return jsonify({"error": str(e)}), 502
    mailer.journaliser("facture", "order", oid, adresse, "envoye", par=user["username"])
    audit("relance facture", "order", oid, f"{bon['po_number']} -> {adresse}")
    return jsonify({"ok": True, "destinataire": adresse})


@bp.get("/relances")
@require("relances.view")
def historique_relances():
    limite = min(int(request.args.get("limite", 200)), 1000)
    lignes = query("SELECT * FROM reminders ORDER BY id DESC LIMIT ?", (limite,))
    return jsonify({"relances": lignes, "messagerie_prete": mailer.messagerie_prete()})
