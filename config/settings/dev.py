from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

if not DEBUG and SECRET_KEY == "insecure-dev-key":  # noqa: F405
    raise ImproperlyConfigured(
        "SECRET_KEY environment variable must be set when DEBUG is disabled."
    )

# The dockerized dev stack runs gunicorn without nginx, so let the app serve
# uploaded media directly (dev-only convenience; real prod needs nginx/S3).
SERVE_MEDIA = True
