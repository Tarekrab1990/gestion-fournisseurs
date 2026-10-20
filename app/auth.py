"""Connexion, déconnexion et changement de mot de passe."""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, session

from .database import query, execute, audit, now, get_settings
from .permissions import modules_for
from .security import (verify_password, hash_password, password_problem,
                       current_user, user_permissions, csrf_token, check_csrf)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

MAX_ECHECS = 5
VERROU_MINUTES = 15


def session_payload(user):
    perms = sorted(user_permissions(user))
    return {
        "utilisateur": {
            "id": user["id"],
            "username": user["username"],
            "nom": user["full_name"] or user["username"],
            "email": user["email"],
            "role": user["role_name"],
            "role_code": user["role_code"],
            "must_change": bool(user["must_change"]),
        },
        "permissions": perms,
        "modules": modules_for(set(perms)),
        "parametres": get_settings(),
        "csrf": csrf_token(),
    }


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Identifiant et mot de passe sont requis."}), 400

    row = query(
        "SELECT u.*, r.code role_code, r.name role_name"
        " FROM users u JOIN roles r ON r.id = u.role_id WHERE u.username = ?",
        (username,), one=True,
    )
    generique = "Identifiant ou mot de passe incorrect."

    if row and row["locked_until"]:
        try:
            until = datetime.fromisoformat(row["locked_until"])
            if until > datetime.now(timezone.utc):
                reste = int((until - datetime.now(timezone.utc)).total_seconds() // 60) + 1
                return jsonify({"error": f"Compte verrouillé. Réessayez dans {reste} minutes."}), 429
        except ValueError:
            pass

    if not row or not verify_password(password, row["password_hash"]):
        if row:
            echecs = row["failed_logins"] + 1
            verrou = None
            if echecs >= MAX_ECHECS:
                verrou = (datetime.now(timezone.utc) + timedelta(minutes=VERROU_MINUTES)).isoformat()
                echecs = 0
            execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                    (echecs, verrou, row["id"]))
            audit("connexion refusée", "user", row["id"], username=username)
        return jsonify({"error": generique}), 401

    if not row["is_active"]:
        return jsonify({"error": "Ce compte est désactivé. Contactez un administrateur."}), 403

    session.clear()
    session["uid"] = row["id"]
    session["username"] = row["username"]
    session.permanent = True
    csrf_token()
    execute("UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = ? WHERE id = ?",
            (now(), row["id"]))
    audit("connexion", "user", row["id"])
    return jsonify(session_payload(current_user()))


@bp.post("/logout")
def logout():
    user = current_user()
    if user and check_csrf():
        audit("déconnexion", "user", user["id"])
    session.clear()
    return jsonify({"ok": True})


@bp.get("/session")
def get_session():
    user = current_user()
    if not user:
        return jsonify({"authenticated": False, "csrf": csrf_token()})
    payload = session_payload(user)
    payload["authenticated"] = True
    return jsonify(payload)


@bp.post("/password")
def change_password():
    user = current_user()
    if not user:
        return jsonify({"error": "authentification requise"}), 401
    if not check_csrf():
        return jsonify({"error": "jeton de sécurité invalide, rechargez la page"}), 403
    data = request.get_json(silent=True) or {}
    ancien, nouveau = data.get("ancien") or "", data.get("nouveau") or ""
    if not verify_password(ancien, user["password_hash"]):
        return jsonify({"error": "Mot de passe actuel incorrect."}), 400
    probleme = password_problem(nouveau)
    if probleme:
        return jsonify({"error": probleme}), 400
    execute("UPDATE users SET password_hash = ?, must_change = 0 WHERE id = ?",
            (hash_password(nouveau), user["id"]))
    audit("mot de passe changé", "user", user["id"])
    return jsonify({"ok": True})
