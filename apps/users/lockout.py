from django.conf import settings
from django.core.cache import cache


def _failures_key(identifier):
    return f"login:failures:{identifier.lower()}"


def _lock_key(identifier):
    return f"login:lock:{identifier.lower()}"


def is_locked(identifier):
    return cache.get(_lock_key(identifier)) is not None


def register_failure(identifier):
    ttl = settings.LOGIN_LOCKOUT_MINUTES * 60
    key = _failures_key(identifier)
    failures = cache.get(key, 0) + 1
    cache.set(key, failures, timeout=ttl)
    if failures >= settings.LOGIN_MAX_FAILURES:
        cache.set(_lock_key(identifier), True, timeout=ttl)
        cache.delete(key)


def reset(identifier):
    cache.delete(_failures_key(identifier))
