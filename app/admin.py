"""Administration : comptes, rôles, départements, paramètres, journal."""

import os
import secrets

from flask import Blueprint, request, jsonify

from .database import (query, execute, get_db, audit, now, get_settings,
                        set_setting, insert_ignore)
from .permissions import PERMISSION_GROUPS, ALL_PERMISSIONS
from .security import (require, current_user, hash_password, password_problem)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

PARAMS_MODIFIABLES = {
    "org_name": ("Nom de l'organisation", "texte"),
    "seuil_devis": ("Seuil du devis comparatif (TTC)", "entier"),
    "devise": ("Devise", "texte"),
    "c20_validite_mois": ("Validité du C20 (mois)", "entier"),
    "c20_preavis_jours": ("Préavis d'expiration du C20 (jours)", "entier"),
    "alerte_debit_jours": ("Alerte si non débité après (jours)", "entier"),
    "validation_paiement": ("Circuit de validation des règlements (1 = actif)", "booleen"),
    "blocage_devis": ("Bloquer la demande si le devis n'est pas conforme", "booleen"),
    "blocage_dossier": ("Bloquer la demande si le dossier fiscal est incomplet", "booleen"),
    "blocage_facture": ("Bloquer la demande sans facture originale", "booleen"),
    "relance_c20_jours": ("Relancer quand le C20 expire dans moins de (jours)", "entier"),
    "relance_intervalle_jours": ("Délai minimum entre deux relances (jours)", "entier"),
}

PARAMS_MESSAGERIE = {
    "smtp_hote": ("Serveur SMTP", "texte"),
    "smtp_port": ("Port SMTP", "entier"),
    "smtp_utilisateur": ("Compte SMTP", "texte_libre"),
    "smtp_tls": ("Chiffrement STARTTLS (1 = actif)", "booleen"),
    "smtp_expediteur": ("Adresse d'expédition", "texte_libre"),
    "smtp_copie": ("Copie systématique à (facultatif)", "texte_libre"),
}


# --- Utilisateurs ------------------------------------------------------------
def user_row(r):
    return {
        "id": r["id"], "username": r["username"], "nom": r["full_name"],
        "email": r["email"], "role_id": r["role_id"], "role": r["role_name"],
        "role_code": r["role_code"], "actif": bool(r["is_active"]),
        "must_change": bool(r["must_change"]),
        "verrouille": bool(r["locked_until"]),
        "derniere_connexion": r["last_login_at"], "cree_le": r["created_at"],
    }


@bp.get("/users")
@require("admin.users")
def list_users():
    rows = query("SELECT u.*, r.name role_name, r.code role_code FROM users u"
                 " JOIN roles r ON r.id = u.role_id ORDER BY u.username")
    roles = query("SELECT id, code, name FROM roles ORDER BY name")
    return jsonify({
        "utilisateurs": [user_row(r) for r in rows],
        "roles": [dict(r) for r in roles],
    })


@bp.post("/users")
@require("admin.users")
def create_user():
    d = request.get_json(silent=True) or {}
    username = (d.get("username") or "").strip()
    if not username or len(username) < 3:
        return jsonify({"error": "L'identifiant doit contenir au moins 3 caractères."}), 400
    if not username.replace(".", "").replace("_", "").replace("-", "").isalnum():
        return jsonify({"error": "L'identifiant n'accepte que lettres, chiffres, point, tiret et souligné."}), 400
    if query("SELECT id FROM users WHERE username = ?", (username,), one=True):
        return jsonify({"error": "Cet identifiant est déjà pris."}), 409
    role = query("SELECT id FROM roles WHERE id = ?", (d.get("role_id"),), one=True)
    if not role:
        return jsonify({"error": "Rôle inconnu."}), 400

    mot_de_passe = d.get("password") or secrets.token_urlsafe(9)
    probleme = password_problem(mot_de_passe)
    if d.get("password") and probleme:
        return jsonify({"error": probleme}), 400

    uid = execute(
        "INSERT INTO users (username, full_name, email, password_hash, role_id, is_active,"
        " must_change, created_at) VALUES (?,?,?,?,?,?,1,?)",
        (username, (d.get("nom") or "").strip(), (d.get("email") or "").strip(),
         hash_password(mot_de_passe), role["id"], 1 if d.get("actif", True) else 0, now()),
    )
    audit("création utilisateur", "user", uid, username)
    return jsonify({"id": uid, "mot_de_passe_provisoire": mot_de_passe}), 201


@bp.put("/users/<int:uid>")
@require("admin.users")
def update_user(uid):
    row = query("SELECT * FROM users WHERE id = ?", (uid,), one=True)
    if not row:
        return jsonify({"error": "Utilisateur introuvable."}), 404
    d = request.get_json(silent=True) or {}
    moi = current_user()

    role_id = d.get("role_id", row["role_id"])
    if not query("SELECT id FROM roles WHERE id = ?", (role_id,), one=True):
        return jsonify({"error": "Rôle inconnu."}), 400
    actif = 1 if d.get("actif", bool(row["is_active"])) else 0

    if row["id"] == moi["id"] and (actif == 0 or role_id != row["role_id"]):
        return jsonify({"error": "Vous ne pouvez pas modifier votre propre rôle ni désactiver votre compte."}), 400
    if actif == 0 or role_id != row["role_id"]:
        admins = query(
            "SELECT COUNT(*) c FROM users u JOIN roles r ON r.id = u.role_id"
            " WHERE r.code = 'ADMIN' AND u.is_active = 1 AND u.id <> ?", (uid,), one=True)["c"]
        etait_admin = query("SELECT code FROM roles WHERE id = ?", (row["role_id"],), one=True)["code"] == "ADMIN"
        if etait_admin and admins == 0:
            return jsonify({"error": "Il doit rester au moins un administrateur actif."}), 400

    execute("UPDATE users SET full_name=?, email=?, role_id=?, is_active=?, locked_until=NULL,"
            " failed_logins=0 WHERE id=?",
            ((d.get("nom") or row["full_name"]).strip(), (d.get("email") or row["email"]).strip(),
             role_id, actif, uid))
    audit("modification utilisateur", "user", uid, row["username"])
    return jsonify({"ok": True})


@bp.post("/users/<int:uid>/password")
@require("admin.users")
def reset_password(uid):
    row = query("SELECT * FROM users WHERE id = ?", (uid,), one=True)
    if not row:
        return jsonify({"error": "Utilisateur introuvable."}), 404
    d = request.get_json(silent=True) or {}
    mot_de_passe = d.get("password") or secrets.token_urlsafe(9)
    if d.get("password"):
        probleme = password_problem(mot_de_passe)
        if probleme:
            return jsonify({"error": probleme}), 400
    execute("UPDATE users SET password_hash=?, must_change=1, failed_logins=0,"
            " locked_until=NULL WHERE id=?", (hash_password(mot_de_passe), uid))
    audit("réinitialisation mot de passe", "user", uid, row["username"])
    return jsonify({"mot_de_passe_provisoire": mot_de_passe})


@bp.delete("/users/<int:uid>")
@require("admin.users")
def delete_user(uid):
    row = query("SELECT u.*, r.code role_code FROM users u JOIN roles r ON r.id=u.role_id"
                " WHERE u.id = ?", (uid,), one=True)
    if not row:
        return jsonify({"error": "Utilisateur introuvable."}), 404
    if uid == current_user()["id"]:
        return jsonify({"error": "Vous ne pouvez pas supprimer votre propre compte."}), 400
    if row["role_code"] == "ADMIN":
        restants = query("SELECT COUNT(*) c FROM users u JOIN roles r ON r.id=u.role_id"
                         " WHERE r.code='ADMIN' AND u.id <> ?", (uid,), one=True)["c"]
        if restants == 0:
            return jsonify({"error": "Il doit rester au moins un administrateur."}), 400
    execute("DELETE FROM users WHERE id = ?", (uid,))
    audit("suppression utilisateur", "user", uid, row["username"])
    return jsonify({"ok": True})


# --- Rôles et permissions ----------------------------------------------------
@bp.get("/roles")
@require("admin.roles")
def list_roles():
    roles = []
    for r in query("SELECT * FROM roles ORDER BY is_system DESC, name"):
        perms = [x["permission"] for x in
                 query("SELECT permission FROM role_permissions WHERE role_id = ?", (r["id"],))]
        nb = query("SELECT COUNT(*) c FROM users WHERE role_id = ?", (r["id"],), one=True)["c"]
        roles.append({"id": r["id"], "code": r["code"], "nom": r["name"],
                      "description": r["description"], "systeme": bool(r["is_system"]),
                      "permissions": perms, "nb_utilisateurs": nb})
    return jsonify({
        "roles": roles,
        "catalogue": [{"groupe": g, "permissions": [{"code": c, "libelle": l} for c, l in p]}
                      for g, p in PERMISSION_GROUPS],
    })


@bp.post("/roles")
@require("admin.roles")
def create_role():
    d = request.get_json(silent=True) or {}
    code = (d.get("code") or "").strip().upper().replace(" ", "_")
    nom = (d.get("nom") or "").strip()
    if not code or not nom:
        return jsonify({"error": "Code et libellé du rôle sont obligatoires."}), 400
    if query("SELECT id FROM roles WHERE code = ?", (code,), one=True):
        return jsonify({"error": "Ce code de rôle existe déjà."}), 409
    rid = execute("INSERT INTO roles (code, name, description, is_system) VALUES (?,?,?,0)",
                  (code, nom, (d.get("description") or "").strip()))
    for p in [p for p in (d.get("permissions") or []) if p in ALL_PERMISSIONS]:
        insert_ignore("role_permissions", ["role_id", "permission"], (rid, p))
    audit("création rôle", "role", rid, code)
    return jsonify({"id": rid}), 201


@bp.put("/roles/<int:rid>")
@require("admin.roles")
def update_role(rid):
    role = query("SELECT * FROM roles WHERE id = ?", (rid,), one=True)
    if not role:
        return jsonify({"error": "Rôle introuvable."}), 404
    d = request.get_json(silent=True) or {}
    demandees = [p for p in (d.get("permissions") or []) if p in ALL_PERMISSIONS]
    if role["code"] == "ADMIN":
        demandees = list(ALL_PERMISSIONS)   # le rôle administrateur garde tout
    execute("UPDATE roles SET name=?, description=? WHERE id=?",
            ((d.get("nom") or role["name"]).strip(),
             (d.get("description") or role["description"]).strip(), rid))
    execute("DELETE FROM role_permissions WHERE role_id = ?", (rid,))
    for p in demandees:
        insert_ignore("role_permissions", ["role_id", "permission"], (rid, p))
    audit("modification rôle", "role", rid, f"{role['code']} — {len(demandees)} permission(s)")
    return jsonify({"ok": True})


@bp.delete("/roles/<int:rid>")
@require("admin.roles")
def delete_role(rid):
    role = query("SELECT * FROM roles WHERE id = ?", (rid,), one=True)
    if not role:
        return jsonify({"error": "Rôle introuvable."}), 404
    if role["is_system"]:
        return jsonify({"error": "Ce rôle est intégré à l'application et ne peut pas être supprimé."}), 400
    nb = query("SELECT COUNT(*) c FROM users WHERE role_id = ?", (rid,), one=True)["c"]
    if nb:
        return jsonify({"error": f"{nb} compte(s) utilisent ce rôle. Réaffectez-les d'abord."}), 400
    execute("DELETE FROM roles WHERE id = ?", (rid,))
    audit("suppression rôle", "role", rid, role["code"])
    return jsonify({"ok": True})


# --- Départements ------------------------------------------------------------
@bp.get("/departments")
@require("admin.departments")
def list_departments():
    rows = query("SELECT * FROM departments ORDER BY name")
    usage = {r["department"]: r["c"] for r in
             query("SELECT department, COUNT(*) c FROM purchase_orders GROUP BY department")}
    return jsonify([{"id": r["id"], "nom": r["name"], "actif": bool(r["is_active"]),
                     "nb_bons": usage.get(r["name"], 0)} for r in rows])


@bp.post("/departments")
@require("admin.departments")
def create_department():
    nom = ((request.get_json(silent=True) or {}).get("nom") or "").strip()
    if not nom:
        return jsonify({"error": "Le nom du département est obligatoire."}), 400
    if query("SELECT id FROM departments WHERE name = ?", (nom,), one=True):
        return jsonify({"error": "Ce département existe déjà."}), 409
    did = execute("INSERT INTO departments (name) VALUES (?)", (nom,))
    audit("création département", "department", did, nom)
    return jsonify({"id": did}), 201


@bp.put("/departments/<int:did>")
@require("admin.departments")
def update_department(did):
    row = query("SELECT * FROM departments WHERE id = ?", (did,), one=True)
    if not row:
        return jsonify({"error": "Département introuvable."}), 404
    d = request.get_json(silent=True) or {}
    nom = (d.get("nom") or row["name"]).strip()
    actif = 1 if d.get("actif", bool(row["is_active"])) else 0
    execute("UPDATE departments SET name=?, is_active=? WHERE id=?", (nom, actif, did))
    if nom != row["name"]:
        execute("UPDATE purchase_orders SET department=? WHERE department=?", (nom, row["name"]))
        execute("UPDATE suppliers SET department=? WHERE department=?", (nom, row["name"]))
    audit("modification département", "department", did, nom)
    return jsonify({"ok": True})


@bp.delete("/departments/<int:did>")
@require("admin.departments")
def delete_department(did):
    row = query("SELECT * FROM departments WHERE id = ?", (did,), one=True)
    if not row:
        return jsonify({"error": "Département introuvable."}), 404
    nb = query("SELECT COUNT(*) c FROM purchase_orders WHERE department = ?",
               (row["name"],), one=True)["c"]
    if nb:
        return jsonify({"error": f"{nb} bon(s) de commande y sont rattachés. "
                                 "Désactivez-le plutôt que de le supprimer."}), 400
    execute("DELETE FROM departments WHERE id = ?", (did,))
    audit("suppression département", "department", did, row["name"])
    return jsonify({"ok": True})


# --- Paramètres --------------------------------------------------------------
@bp.get("/settings")
@require("admin.settings")
def read_settings():
    from . import mailer
    valeurs = get_settings()
    return jsonify({
        "valeurs": valeurs,
        "champs": [{"cle": k, "libelle": v[0], "type": v[1]} for k, v in PARAMS_MODIFIABLES.items()],
        "messagerie": [{"cle": k, "libelle": v[0], "type": v[1]} for k, v in PARAMS_MESSAGERIE.items()],
        "messagerie_prete": mailer.messagerie_prete(valeurs),
        "mot_de_passe_smtp_present": bool(os.environ.get("SMTP_PASSWORD")),
    })


@bp.put("/settings")
@require("admin.settings")
def write_settings():
    d = request.get_json(silent=True) or {}
    champs = dict(PARAMS_MODIFIABLES)
    champs.update(PARAMS_MESSAGERIE)
    modifs = []
    for cle, valeur in d.items():
        if cle not in champs:
            continue
        libelle, typ = champs[cle]
        if typ == "booleen":
            valeur = "1" if str(valeur) in ("1", "true", "True", "oui", "on") else "0"
        elif typ == "texte_libre":
            valeur = str(valeur).strip()
        elif typ == "entier":
            try:
                n = int(float(valeur))
            except (TypeError, ValueError):
                return jsonify({"error": f"{libelle} : valeur numérique attendue."}), 400
            if n < 0:
                return jsonify({"error": f"{libelle} : valeur négative refusée."}), 400
            valeur = str(n)
        else:
            valeur = str(valeur).strip()
            if not valeur:
                return jsonify({"error": f"{libelle} : valeur vide refusée."}), 400
        set_setting(cle, valeur)
        modifs.append(f"{cle}={valeur}")
    if modifs:
        audit("modification paramètres", "settings", "", ", ".join(modifs))
    return jsonify({"ok": True, "valeurs": get_settings()})


# --- Journal d'audit ---------------------------------------------------------
@bp.get("/audit")
@require("admin.audit")
def read_audit():
    limite = min(int(request.args.get("limite", 200)), 1000)
    recherche = (request.args.get("q") or "").strip()
    sql = "SELECT * FROM audit_log"
    args = []
    if recherche:
        sql += " WHERE username LIKE ? OR action LIKE ? OR details LIKE ?"
        args = [f"%{recherche}%"] * 3
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limite)
    return jsonify([dict(r) for r in query(sql, tuple(args))])


# --- Jeu d'essai -------------------------------------------------------------
@bp.post("/demo")
@require("admin.settings")
def load_demo():
    from .demo import charger_jeu_essai
    if query("SELECT COUNT(*) c FROM suppliers", one=True)["c"]:
        return jsonify({"error": "La base contient déjà des fournisseurs."}), 400
    n = charger_jeu_essai(current_user()["username"])
    audit("import du jeu d'essai", "demo", "", f"{n} enregistrements")
    return jsonify({"ok": True, "enregistrements": n})


# --- test de la messagerie ---------------------------------------------------
@bp.post("/mail/test")
@require("admin.mail")
def tester_messagerie():
    from . import mailer
    d = request.get_json(silent=True) or {}
    destinataire = (d.get("destinataire") or current_user()["email"] or "").strip()
    if not destinataire:
        return jsonify({"error": "Indiquez une adresse de destination."}), 400
    settings = get_settings()
    try:
        mailer.envoyer(destinataire,
                       "Test de configuration — suivi des fournisseurs",
                       "Ce message confirme que l'application peut envoyer des courriels.\n\n"
                       "Si vous le recevez, la configuration SMTP est correcte.\n",
                       settings)
    except mailer.ErreurMessagerie as e:
        mailer.journaliser("test", "", 0, destinataire, "echec", str(e),
                           par=current_user()["username"])
        return jsonify({"error": str(e)}), 502
    mailer.journaliser("test", "", 0, destinataire, "envoye", par=current_user()["username"])
    audit("test de messagerie", "settings", "", destinataire)
    return jsonify({"ok": True, "destinataire": destinataire})
