#!/usr/bin/env python3
"""Démarrage en développement : python run.py

En production, servez plutôt via gunicorn/waitress (voir README.md).
"""
import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"Application disponible sur http://{host}:{port}")
    app.run(host=host, port=port, debug=os.environ.get("DEBUG") == "1")
