from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

if not DEBUG and SECRET_KEY == "insecure-dev-key":  # noqa: F405
    raise ImproperlyConfigured(
        "SECRET_KEY environment variable must be set when DEBUG is disabled."
    )
