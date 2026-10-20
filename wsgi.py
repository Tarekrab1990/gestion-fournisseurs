"""Point d'entrée WSGI pour gunicorn / waitress / mod_wsgi."""
from app import create_app

application = create_app()
app = application
