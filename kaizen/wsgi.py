"""kaizen/wsgi.py — Gunicorn / WSGI entry point"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kaizen.settings")
application = get_wsgi_application()
