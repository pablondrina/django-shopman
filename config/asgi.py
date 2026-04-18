"""ASGI config for the Shopman project.

Exposed as ``application`` so daphne (or any ASGI server) can serve the
django-eventstream SSE endpoints alongside regular Django views. WSGI
remains available for projects that don't need streaming.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()
