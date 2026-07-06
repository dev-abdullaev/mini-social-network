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
    cache.add(key, 0, timeout=ttl)
    try:
        failures = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=ttl)
        failures = 1
    if failures >= settings.LOGIN_MAX_FAILURES:
        cache.set(_lock_key(identifier), True, timeout=ttl)
        cache.delete(key)


def reset(identifier):
    cache.delete(_failures_key(identifier))
