"""Pièces jointes — C20 scannés, factures originales, devis comparatifs.

Les fichiers sont écrits sur disque sous DATA_DIR/pieces-jointes, jamais dans
la base : une sauvegarde du dossier de données suffit à tout reprendre.
Le nom d'origine n'est utilisé que pour l'affichage et le téléchargement ; le
nom sur disque est dérivé de l'empreinte du contenu.
"""

import os
import hashlib
import unicodedata

from flask import Blueprint, request, jsonify, send_file, current_app

from .database import query, execute, audit, now, get_settings
from .security import current_user, user_permissions, require, login_required

bp = Blueprint("pieces", __name__, url_prefix="/api/pieces")

TYPES_AUTORISES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/tiff": ".tif",
}
EXTENSIONS_AUTORISEES = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
TAILLE_MAX = 10 * 1024 * 1024        # 10 Mo par fichier

# Nature de la pièce -> permission d'écriture exigée en plus de pieces.upload
NATURES = {
    "c20":     ("C20 / extrait de rôle", "fournisseurs.edit"),
    "rc":      ("RC / agrément", "fournisseurs.edit"),
    "rib":     ("RIB", "fournisseurs.edit"),
    "bon":     ("Bon de commande signé", "bons.edit"),
    "facture": ("Facture originale", "factures.edit"),
    "devis":   ("Devis comparatif", "devis.edit"),
    "paiement": ("Justificatif de règlement", "paiements.edit"),
    "autre":   ("Autre document", "bons.edit"),
}
ENTITES = {"supplier": "suppliers", "order": "purchase_orders"}


def dossier_pieces():
    chemin = os.path.join(current_app.config["DATA_DIR"], "pieces-jointes")
    os.makedirs(chemin, exist_ok=True)
    return chemin


def nom_sain(nom):
    """Nom de fichier affichable : sans accents, sans séparateur de chemin."""
    nom = os.path.basename(nom or "document")
    nom = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    nom = "".join(c for c in nom if c.isalnum() or c in " ._-()").strip()
    return (nom or "document")[:120]


def entite_existe(entity, entity_id):
    table = ENTITES.get(entity)
    if not table:
        return False
    return bool(query(f"SELECT id FROM {table} WHERE id = ?", (entity_id,), one=True))


def lister(entity, entity_id):
    rows = query("SELECT id, kind, filename, mime, size_bytes, uploaded_by, uploaded_at"
                 " FROM attachments WHERE entity = ? AND entity_id = ? ORDER BY id DESC",
                 (entity, entity_id))
    for r in rows:
        r["nature"] = NATURES.get(r["kind"], NATURES["autre"])[0]
    return rows


@bp.get("")
@require("pieces.view")
def liste():
    entity = request.args.get("entity", "")
    try:
        entity_id = int(request.args.get("entity_id", "0"))
    except ValueError:
        return jsonify({"error": "Identifiant invalide."}), 400
    if entity not in ENTITES:
        return jsonify({"error": "Objet inconnu."}), 400
    return jsonify(lister(entity, entity_id))


@bp.post("")
@require("pieces.upload")
def deposer():
    entity = request.form.get("entity", "")
    kind = request.form.get("kind", "autre")
    try:
        entity_id = int(request.form.get("entity_id", "0"))
    except ValueError:
        return jsonify({"error": "Identifiant invalide."}), 400

    if entity not in ENTITES:
        return jsonify({"error": "Objet inconnu."}), 400
    if kind not in NATURES:
        return jsonify({"error": "Nature de document inconnue."}), 400
    if not entite_existe(entity, entity_id):
        return jsonify({"error": "L'enregistrement visé n'existe pas."}), 404

    besoin = NATURES[kind][1]
    if besoin not in user_permissions(current_user()):
        return jsonify({"error": "Votre rôle ne permet pas de joindre ce type de document.",
                        "missing": [besoin]}), 403

    fichier = request.files.get("fichier")
    if not fichier or not fichier.filename:
        return jsonify({"error": "Aucun fichier reçu."}), 400

    donnees = fichier.read(TAILLE_MAX + 1)
    if len(donnees) > TAILLE_MAX:
        return jsonify({"error": f"Fichier trop volumineux (maximum {TAILLE_MAX // 1024 // 1024} Mo)."}), 413
    if not donnees:
        return jsonify({"error": "Le fichier est vide."}), 400

    affichable = nom_sain(fichier.filename)
    ext = os.path.splitext(affichable)[1].lower()
    mime = (fichier.mimetype or "").split(";")[0].strip().lower()
    if ext not in EXTENSIONS_AUTORISEES or mime not in TYPES_AUTORISES:
        return jsonify({"error": "Formats acceptés : PDF, JPEG, PNG, WEBP, TIFF."}), 415
    # cohérence entre l'extension annoncée et le contenu réel
    entete = donnees[:8]
    signatures = {b"%PDF": ".pdf", b"\xff\xd8\xff": ".jpg", b"\x89PNG": ".png"}
    for signature, attendu in signatures.items():
        if entete.startswith(signature):
            if attendu == ".jpg" and ext in (".jpg", ".jpeg"):
                break
            if attendu != ".jpg" and ext != attendu:
                return jsonify({"error": "Le contenu du fichier ne correspond pas à son extension."}), 415
            break

    empreinte = hashlib.sha256(donnees).hexdigest()
    stocke = empreinte[:32] + TYPES_AUTORISES.get(mime, ext)
    chemin = os.path.join(dossier_pieces(), stocke)
    if not os.path.exists(chemin):
        with open(chemin, "wb") as fh:
            fh.write(donnees)
        try:
            os.chmod(chemin, 0o640)
        except OSError:
            pass

    user = current_user()
    pid = execute("INSERT INTO attachments (entity, entity_id, kind, filename, stored_name, mime,"
                  " size_bytes, sha256, uploaded_by, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (entity, entity_id, kind, affichable, stocke, mime, len(donnees),
                   empreinte, user["username"], now()))
    audit("dépôt de pièce jointe", entity, entity_id, f"{NATURES[kind][0]} — {affichable}")
    return jsonify({"id": pid, "filename": affichable}), 201


@bp.get("/<int:pid>")
@require("pieces.view")
def telecharger(pid):
    row = query("SELECT * FROM attachments WHERE id = ?", (pid,), one=True)
    if not row:
        return jsonify({"error": "Pièce jointe introuvable."}), 404
    chemin = os.path.join(dossier_pieces(), row["stored_name"])
    if not os.path.exists(chemin):
        return jsonify({"error": "Le fichier est absent du serveur. Restaurez-le depuis une sauvegarde."}), 410
    audit("téléchargement de pièce jointe", row["entity"], row["entity_id"], row["filename"])
    return send_file(chemin, mimetype=row["mime"], as_attachment=True,
                     download_name=row["filename"], max_age=0)


@bp.delete("/<int:pid>")
@require("pieces.delete")
def supprimer(pid):
    row = query("SELECT * FROM attachments WHERE id = ?", (pid,), one=True)
    if not row:
        return jsonify({"error": "Pièce jointe introuvable."}), 404
    execute("DELETE FROM attachments WHERE id = ?", (pid,))
    # le fichier n'est effacé que si plus aucune fiche ne le référence
    reste = query("SELECT COUNT(*) AS c FROM attachments WHERE stored_name = ?",
                  (row["stored_name"],), one=True)["c"]
    if int(reste) == 0:
        try:
            os.remove(os.path.join(dossier_pieces(), row["stored_name"]))
        except OSError:
            pass
    audit("suppression de pièce jointe", row["entity"], row["entity_id"], row["filename"])
    return jsonify({"ok": True})


def compter_par_entite(entity):
    """{id de l'objet: nombre de pièces} — pour marquer les lignes des tableaux."""
    rows = query("SELECT entity_id, COUNT(*) AS c FROM attachments WHERE entity = ?"
                 " GROUP BY entity_id", (entity,))
    return {int(r["entity_id"]): int(r["c"]) for r in rows}
