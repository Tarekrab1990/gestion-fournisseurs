"""Mots de passe, jeton CSRF et contrôle des permissions."""

import hmac
import base64
import hashlib
import secrets
from functools import wraps

from flask import session, jsonify, request

PBKDF2_ROUNDS = 260_000


# --- Mots de passe ----------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ROUNDS,
        base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(rounds)
        )
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def password_problem(password: str):
    """Politique de mot de passe. Renvoie None si le mot de passe convient."""
    if len(password or "") < 10:
        return "Le mot de passe doit contenir au moins 10 caractères."
    if password.isdigit() or password.isalpha():
        return "Mélangez lettres et chiffres."
    return None


# --- CSRF -------------------------------------------------------------------
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    sent = request.headers.get("X-CSRF-Token", "")
    return bool(sent) and hmac.compare_digest(sent, session.get("csrf", ""))


# --- Session et permissions -------------------------------------------------
def current_user():
    from .database import query
    uid = session.get("uid")
    if not uid:
        return None
    row = query(
        "SELECT u.*, r.code role_code, r.name role_name"
        " FROM users u JOIN roles r ON r.id = u.role_id WHERE u.id = ?",
        (uid,), one=True,
    )
    if not row or not row["is_active"]:
        return None
    return row


def user_permissions(user):
    from .database import query
    if not user:
        return set()
    rows = query("SELECT permission FROM role_permissions WHERE role_id = ?", (user["role_id"],))
    return {r["permission"] for r in rows}


def has_perm(perm):
    return perm in user_permissions(current_user())


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return jsonify({"error": "authentification requise"}), 401
        if not check_csrf():
            return jsonify({"error": "jeton de sécurité invalide, rechargez la page"}), 403
        return fn(*a, **kw)
    return wrapper


def require(*perms):
    """Exige toutes les permissions listées."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            user = current_user()
            if not user:
                return jsonify({"error": "authentification requise"}), 401
            if not check_csrf():
                return jsonify({"error": "jeton de sécurité invalide, rechargez la page"}), 403
            held = user_permissions(user)
            missing = [p for p in perms if p not in held]
            if missing:
                return jsonify({
                    "error": "Votre rôle ne permet pas cette action.",
                    "missing": missing,
                }), 403
            return fn(*a, **kw)
        return wrapper
    return deco
