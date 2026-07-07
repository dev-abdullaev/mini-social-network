from .base import *  # noqa: F403

SECRET_KEY = "test-only-secret-key-" + "x" * 48

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# No collectstatic runs in the test env, so drop WhiteNoise (static isn't exercised).
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m.lower()]  # noqa: F405
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {"login": "1000/min", "register": "1000/min"},
}
