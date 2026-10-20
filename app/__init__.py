"""Fabrique de l'application Flask."""

import os
import secrets
from datetime import timedelta

from flask import Flask, render_template, jsonify, request, send_from_directory

from .database import init_db, close_db
from .security import csrf_token, current_user

__version__ = "2.0.0"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _secret_key(data_dir):
    """Clé de session : variable d'environnement, sinon fichier persistant."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = os.path.join(data_dir, "secret.key")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    key = secrets.token_urlsafe(48)
    os.makedirs(data_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def create_app(config=None):
    app = Flask(__name__, static_folder="static", template_folder="templates")

    data_dir = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
    app.config.update(
        DATA_DIR=data_dir,
        DATABASE=os.environ.get("DATABASE", os.path.join(data_dir, "gestion.db")),
        SECRET_KEY=_secret_key(data_dir),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=int(os.environ.get("SESSION_HOURS", "10"))),
        MAX_CONTENT_LENGTH=12 * 1024 * 1024,
        JSON_AS_ASCII=False,
        VERSION=__version__,
    )
    if config:
        app.config.update(config)

    app.teardown_appcontext(close_db)

    from .auth import bp as auth_bp
    from .api import bp as api_bp
    from .admin import bp as admin_bp
    from .attachments import bp as pieces_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(pieces_bp)

    @app.get("/")
    def index():
        return render_template("index.html", version=__version__)

    @app.get("/sante")
    def sante():
        return jsonify({"statut": "ok", "version": __version__})

    @app.after_request
    def entetes(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'self'",
        )
        return resp

    @app.errorhandler(404)
    def not_found(_):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Ressource introuvable."}), 404
        return render_template("index.html", version=__version__), 200

    @app.errorhandler(413)
    def trop_gros(_):
        return jsonify({"error": "Fichier trop volumineux (maximum 10 Mo)."}), 413

    @app.errorhandler(500)
    def erreur(_):
        return jsonify({"error": "Erreur interne du serveur."}), 500

    init_db(app)
    return app
