# Mini Social Network Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Django/DRF backend for a mini social network: JWT auth, email verification (Gmail SMTP), posts/comments/likes, feed, Celery+Redis background cleanup, Docker, tests, CI.

**Architecture:** Single Django project `config/` with three apps under `apps/` (`core` = shared DRF utilities, `users` = auth/verification/cleanup, `posts` = posts/comments/likes/feed). PostgreSQL storage, Redis as Celery broker + Django cache, Celery beat for periodic cleanup. All config via env vars.

**Tech Stack:** Python 3.12, Django 5.1, DRF 3.15, djangorestframework-simplejwt, drf-spectacular, django-filter, Celery 5, Redis, PostgreSQL 16, pytest + pytest-django + factory_boy, ruff, Docker + docker-compose, GitHub Actions.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-06-mini-social-network-design.md`
- All primary keys are UUID (`uuid.uuid4`).
- Validation limits (exact): username 3–32 chars `[A-Za-z0-9_]+` unique; full_name 2–100 chars (latin/cyrillic letters, spaces, hyphens); title 5–255; post content ≤ 10000; comment content ≤ 2000; email valid format, unique.
- Permission rules: anonymous = read-only; authenticated unverified = read + like/unlike only (403 on creating posts/comments); verified = CRUD own content; edit/delete only own entities (403 otherwise).
- Like rules: no self-like (403), no double-like (400, DB unique constraint as backstop), unlike nonexistent like → 404.
- API base prefix `/api/`. DRF default trailing slashes.
- Env defaults: `VERIFICATION_TOKEN_TTL_HOURS=24`, `UNVERIFIED_USER_TTL_HOURS=24`, `POST_TTL_DAYS=0` (disabled), `LOGIN_MAX_FAILURES=5`, `LOGIN_LOCKOUT_MINUTES=15`.
- Run commands with the project venv: `.venv/bin/python`, `.venv/bin/pytest`. Postgres+Redis for local dev/tests come from `docker compose up -d db redis` (ports 5432/6379 on localhost).
- Formatting/linting: ruff only (lint + format). Line length 100.
- Every commit message ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.gitignore`, `.env.example`, `docker-compose.yml`, `manage.py`, `config/__init__.py`, `config/settings.py`, `config/settings_test.py`, `config/urls.py`, `config/wsgi.py`, `config/celery.py`, `apps/__init__.py`, `apps/core/__init__.py`, `apps/core/apps.py`, `apps/core/pagination.py`, `apps/core/permissions.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_sanity.py`

**Interfaces:**
- Produces: `config.settings` (env-driven), `config.celery.app` Celery instance, `apps.core.pagination.DefaultPagination`, `apps.core.permissions.IsVerified` / `IsOwnerOrReadOnly`, pytest wired to `config.settings_test`, running Postgres+Redis containers.

- [ ] **Step 1: Create dependency and tooling files**

`requirements.txt`:
```
Django>=5.1,<5.2
djangorestframework>=3.15,<3.17
djangorestframework-simplejwt>=5.4,<5.6
drf-spectacular>=0.28
django-filter>=24.3
celery[redis]>=5.4,<5.6
redis>=5.2
django-redis>=5.4
psycopg[binary]>=3.2
gunicorn>=23
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.3
pytest-django>=4.9
factory_boy>=3.3
ruff>=0.8
```

`pyproject.toml`:
```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings_test"
python_files = ["test_*.py"]
testpaths = ["tests"]
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
.ruff_cache/
staticfiles/
```

`.env.example`:
```
SECRET_KEY=change-me
DEBUG=1
ALLOWED_HOSTS=localhost,127.0.0.1
SITE_URL=http://localhost:8000

POSTGRES_DB=social
POSTGRES_USER=social
POSTGRES_PASSWORD=social
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

REDIS_URL=redis://localhost:6379/0

EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

VERIFICATION_TOKEN_TTL_HOURS=24
UNVERIFIED_USER_TTL_HOURS=24
POST_TTL_DAYS=0
LOGIN_MAX_FAILURES=5
LOGIN_LOCKOUT_MINUTES=15
LOGIN_THROTTLE_RATE=10/min
ACCESS_TOKEN_LIFETIME_MIN=30
REFRESH_TOKEN_LIFETIME_DAYS=7
```

`docker-compose.yml` (db + redis only for now; Task 14 adds app services):
```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-social}
      POSTGRES_USER: ${POSTGRES_USER:-social}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-social}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-social}"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  pgdata:
```

- [ ] **Step 2: Create Django project files**

`manage.py`:
```python
#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
```

`config/__init__.py`:
```python
from .celery import app as celery_app

__all__ = ("celery_app",)
```

`config/celery.py`:
```python
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

`config/settings.py`:
```python
import os
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-dev-key")
DEBUG = os.environ.get("DEBUG", "0") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "apps.core",
    "apps.users",
    "apps.posts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "social"),
        "USER": os.environ.get("POSTGRES_USER", "social"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "social"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "login": os.environ.get("LOGIN_THROTTLE_RATE", "10/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.environ.get("ACCESS_TOKEN_LIFETIME_MIN", "30"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.environ.get("REFRESH_TOKEN_LIFETIME_DAYS", "7"))
    ),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Mini Social Network API",
    "DESCRIPTION": "Users, posts, comments, likes with JWT auth and email verification.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BEAT_SCHEDULE = {
    "cleanup-unverified-users": {
        "task": "apps.users.tasks.cleanup_unverified_users",
        "schedule": crontab(minute=0),
    },
    "cleanup-old-posts": {
        "task": "apps.posts.tasks.cleanup_old_posts",
        "schedule": crontab(minute=30, hour=3),
    },
}

EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
if EMAIL_HOST_USER:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = True
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or "noreply@example.com"

VERIFICATION_TOKEN_TTL_HOURS = int(os.environ.get("VERIFICATION_TOKEN_TTL_HOURS", "24"))
UNVERIFIED_USER_TTL_HOURS = int(os.environ.get("UNVERIFIED_USER_TTL_HOURS", "24"))
POST_TTL_DAYS = int(os.environ.get("POST_TTL_DAYS", "0"))
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))
```

Note: `apps.users` and `apps.posts` are referenced in `INSTALLED_APPS` but created in this task as empty packages so Django boots (models arrive in Tasks 2 and 7).

`config/settings_test.py`:
```python
from .settings import *  # noqa: F403

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {"login": "1000/min"},
}
```

`config/urls.py`:
```python
from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
```

`config/wsgi.py`:
```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
```

- [ ] **Step 3: Create apps packages and core utilities**

Create empty files: `apps/__init__.py`, `apps/core/__init__.py`, `tests/__init__.py`.
Also create empty app packages so settings import works: `apps/users/__init__.py`, `apps/users/apps.py`, `apps/posts/__init__.py`, `apps/posts/apps.py`.

`apps/core/apps.py`:
```python
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
```

`apps/users/apps.py`:
```python
from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "apps.users"
```

`apps/posts/apps.py`:
```python
from django.apps import AppConfig


class PostsConfig(AppConfig):
    name = "apps.posts"
```

`apps/core/pagination.py`:
```python
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100
```

`apps/core/permissions.py`:
```python
from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsVerified(BasePermission):
    """Write access requires a verified email; reads are always allowed."""

    message = "Email verification required."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user.is_authenticated and request.user.is_verified)


class IsOwnerOrReadOnly(BasePermission):
    """Object writes are allowed only for the author."""

    message = "You can only modify your own content."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.author_id == request.user.id
```

`tests/conftest.py`:
```python
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()
```

`tests/test_sanity.py`:
```python
from django.conf import settings


def test_settings_load():
    assert settings.AUTH_USER_MODEL == "users.User"
```

- [ ] **Step 4: Create venv, install deps, start services**

Run:
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
docker compose up -d db redis
```
Expected: pip install succeeds; `docker compose ps` shows db and redis healthy.

- [ ] **Step 5: Verify Django boots and sanity test passes**

Run: `.venv/bin/python manage.py check`
Expected: `System check identified no issues (0 silenced).`

Run: `.venv/bin/pytest tests/test_sanity.py -v`
Expected: PASS (pytest-django creates the test DB against localhost Postgres).

Run: `.venv/bin/ruff check . && .venv/bin/ruff format .`
Expected: no errors; files formatted.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: scaffold Django project with DRF, Celery, Redis, pytest"
```

---

### Task 2: User and EmailVerificationToken models

**Files:**
- Create: `apps/users/managers.py`, `apps/users/models.py`, `apps/users/migrations/` (generated), `tests/factories.py`
- Test: `tests/test_users_models.py`

**Interfaces:**
- Produces: `apps.users.models.User` (UUID pk, `email`, `username`, `full_name`, `is_verified`, `is_active`, `is_staff`, `created_at`, `updated_at`; `USERNAME_FIELD="email"`), `User.objects.create_user(email, username, full_name, password)`, `apps.users.models.EmailVerificationToken` with `EmailVerificationToken.issue(user) -> EmailVerificationToken` and property `is_valid -> bool`, `tests.factories.UserFactory` (verified by default; `UserFactory(is_verified=False)` for unverified).

- [ ] **Step 1: Write the failing tests**

`tests/factories.py`:
```python
import factory
from django.contrib.auth import get_user_model

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.Sequence(lambda n: f"user{n}")
    full_name = factory.Faker("name")
    is_verified = True
    password = factory.PostGenerationMethodCall("set_password", "password123")
```

`tests/test_users_models.py`:
```python
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.users.models import EmailVerificationToken, User
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_create_user_hashes_password():
    user = User.objects.create_user(
        email="a@example.com", username="alice", full_name="Alice A", password="secret123"
    )
    assert user.password != "secret123"
    assert user.check_password("secret123")
    assert user.is_verified is False


def test_email_unique():
    UserFactory(email="dup@example.com")
    with pytest.raises(IntegrityError):
        UserFactory(email="dup@example.com")


def test_issue_verification_token():
    user = UserFactory(is_verified=False)
    token = EmailVerificationToken.issue(user)
    assert token.is_valid
    assert len(token.token) >= 32
    assert token.expires_at > timezone.now()


def test_expired_token_invalid():
    user = UserFactory(is_verified=False)
    token = EmailVerificationToken.issue(user)
    token.expires_at = timezone.now() - timedelta(minutes=1)
    token.save()
    assert not token.is_valid


def test_used_token_invalid():
    user = UserFactory(is_verified=False)
    token = EmailVerificationToken.issue(user)
    token.used_at = timezone.now()
    token.save()
    assert not token.is_valid
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_users_models.py -v`
Expected: FAIL — `ImportError` (no `apps.users.models`).

- [ ] **Step 3: Implement models**

`apps/users/managers.py`:
```python
from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, username, full_name, password, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        user = self.model(
            email=self.normalize_email(email),
            username=username,
            full_name=full_name,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, full_name, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_verified", True)
        return self.create_user(email, username, full_name, password, **extra_fields)
```

`apps/users/models.py`:
```python
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=32, unique=True)
    full_name = models.CharField(max_length=100)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "full_name"]

    def __str__(self):
        return self.username


class EmailVerificationToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="verification_tokens"
    )
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, user):
        return cls.objects.create(
            user=user,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now()
            + timedelta(hours=settings.VERIFICATION_TOKEN_TTL_HOURS),
        )

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()
```

- [ ] **Step 4: Generate migrations, run tests**

Run:
```bash
.venv/bin/python manage.py makemigrations users
.venv/bin/pytest tests/test_users_models.py -v
```
Expected: migration `apps/users/migrations/0001_initial.py` created; all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add custom User model and EmailVerificationToken"
```

---

### Task 3: Registration endpoint + verification email task

**Files:**
- Create: `apps/users/serializers.py`, `apps/users/tasks.py`, `apps/users/views.py`, `apps/users/auth_urls.py`
- Modify: `config/urls.py`
- Test: `tests/test_auth_register.py`

**Interfaces:**
- Consumes: `User`, `EmailVerificationToken.issue`, `UserFactory`.
- Produces: `POST /api/auth/register/` (fields: `email`, `username`, `full_name`, `password`; 201 → UserSerializer payload), `apps.users.serializers.UserSerializer` (fields `id, email, username, full_name, is_verified, created_at`), `apps.users.tasks.send_verification_email(user_id: str, token: str)` Celery task, `apps/users/auth_urls.py` url module mounted at `/api/auth/`.

- [ ] **Step 1: Write the failing tests**

`tests/test_auth_register.py`:
```python
import pytest
from django.core import mail

from apps.users.models import User
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

REGISTER_URL = "/api/auth/register/"

PAYLOAD = {
    "email": "new@example.com",
    "username": "newuser",
    "full_name": "New User",
    "password": "strongPass123",
}


def test_register_success(api_client):
    response = api_client.post(REGISTER_URL, PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new@example.com"
    assert data["is_verified"] is False
    assert "password" not in data
    user = User.objects.get(email="new@example.com")
    assert user.check_password("strongPass123")
    assert user.verification_tokens.count() == 1
    assert len(mail.outbox) == 1
    assert user.verification_tokens.first().token in mail.outbox[0].body


def test_register_duplicate_email(api_client):
    UserFactory(email="new@example.com")
    response = api_client.post(REGISTER_URL, PAYLOAD)
    assert response.status_code == 400
    assert "email" in response.json()


def test_register_duplicate_username(api_client):
    UserFactory(username="newuser")
    response = api_client.post(REGISTER_URL, PAYLOAD)
    assert response.status_code == 400
    assert "username" in response.json()


@pytest.mark.parametrize(
    "field,value",
    [
        ("email", "not-an-email"),
        ("username", "ab"),
        ("username", "x" * 33),
        ("username", "bad name!"),
        ("full_name", "A"),
        ("full_name", "X" * 101),
        ("full_name", "Name123"),
    ],
)
def test_register_validation_errors(api_client, field, value):
    payload = {**PAYLOAD, field: value}
    response = api_client.post(REGISTER_URL, payload)
    assert response.status_code == 400
    assert field in response.json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_auth_register.py -v`
Expected: FAIL — 404 on `/api/auth/register/` (route not mounted).

- [ ] **Step 3: Implement serializers, task, view, urls**

`apps/users/serializers.py` (note: the explicit `username` field override drops the `UniqueValidator` that `ModelSerializer` would auto-generate from the model's `unique=True`, so it is added back manually; `email` keeps its auto-generated one):
```python
from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import User

USERNAME_VALIDATOR = RegexValidator(
    regex=r"^[A-Za-z0-9_]+$",
    message="Username may contain only latin letters, digits and underscores.",
)
FULL_NAME_VALIDATOR = RegexValidator(
    regex=r"^[A-Za-zА-Яа-яЁё\s-]+$",
    message="Full name may contain only letters, spaces and hyphens.",
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "full_name", "is_verified", "created_at"]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        min_length=3,
        max_length=32,
        validators=[USERNAME_VALIDATOR, UniqueValidator(queryset=User.objects.all())],
    )
    full_name = serializers.CharField(
        min_length=2, max_length=100, validators=[FULL_NAME_VALIDATOR]
    )
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["email", "username", "full_name", "password"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
```

`apps/users/tasks.py`:
```python
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from .models import User


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_verification_email(self, user_id, token):
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return
    verify_url = f"{settings.SITE_URL}/api/auth/verify-email/?token={token}"
    try:
        send_mail(
            subject="Verify your email",
            message=(
                f"Hi {user.username},\n\n"
                f"Confirm your email by opening this link:\n{verify_url}\n\n"
                f"The link expires in {settings.VERIFICATION_TOKEN_TTL_HOURS} hours."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
    except Exception as exc:
        raise self.retry(exc=exc) from exc
```

`apps/users/views.py`:
```python
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import EmailVerificationToken
from .serializers import RegisterSerializer, UserSerializer
from .tasks import send_verification_email


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token = EmailVerificationToken.issue(user)
        send_verification_email.delay(str(user.id), token.token)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
```

`apps/users/auth_urls.py`:
```python
from django.urls import path

from .views import RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
]
```

`config/urls.py` — add the include (full file):
```python
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("api/auth/", include("apps.users.auth_urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_auth_register.py -v`
Expected: all PASS (Celery eager mode executes the email task inline; locmem backend captures it in `mail.outbox`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: registration endpoint with async verification email"
```

---

### Task 4: Login (email or username), refresh, /auth/me

**Files:**
- Modify: `apps/users/serializers.py`, `apps/users/views.py`, `apps/users/auth_urls.py`
- Test: `tests/test_auth_login.py`

**Interfaces:**
- Consumes: `User`, `UserFactory`, `UserSerializer`.
- Produces: `POST /api/auth/login/` (accepts `{"email", "password"}` or `{"username", "password"}` → `{"access": ..., "refresh": ...}`; 401 on bad credentials), `POST /api/auth/refresh/`, `GET /api/auth/me/` (JWT required → UserSerializer payload). Also `apps.users.views.LoginView` (Task 13 modifies it to add lockout/throttle).

- [ ] **Step 1: Write the failing tests**

`tests/test_auth_login.py`:
```python
import pytest

from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"
ME_URL = "/api/auth/me/"


@pytest.fixture
def user():
    return UserFactory(email="kam@example.com", username="kamran")


def test_login_with_email(api_client, user):
    response = api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "password123"})
    assert response.status_code == 200
    assert "access" in response.json()
    assert "refresh" in response.json()


def test_login_with_username(api_client, user):
    response = api_client.post(LOGIN_URL, {"username": "kamran", "password": "password123"})
    assert response.status_code == 200
    assert "access" in response.json()


def test_login_wrong_password(api_client, user):
    response = api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "wrong"})
    assert response.status_code == 401


def test_login_missing_identifier(api_client, user):
    response = api_client.post(LOGIN_URL, {"password": "password123"})
    assert response.status_code == 400


def test_refresh_token(api_client, user):
    tokens = api_client.post(
        LOGIN_URL, {"email": "kam@example.com", "password": "password123"}
    ).json()
    response = api_client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]})
    assert response.status_code == 200
    assert "access" in response.json()


def test_me_with_valid_token(api_client, user):
    tokens = api_client.post(
        LOGIN_URL, {"email": "kam@example.com", "password": "password123"}
    ).json()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    response = api_client.get(ME_URL)
    assert response.status_code == 200
    assert response.json()["username"] == "kamran"


def test_me_with_invalid_token(api_client):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
    response = api_client.get(ME_URL)
    assert response.status_code == 401


def test_me_without_token(api_client):
    response = api_client.get(ME_URL)
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_auth_login.py -v`
Expected: FAIL — 404 (routes not mounted).

- [ ] **Step 3: Implement login serializer and views**

Append to `apps/users/serializers.py`:
```python
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    username = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("username"):
            raise serializers.ValidationError("Provide email or username.")
        return attrs
```

Append to `apps/users/views.py` (add imports at top of file):
```python
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .serializers import LoginSerializer


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("email"):
            user = User.objects.filter(email__iexact=data["email"]).first()
        else:
            user = User.objects.filter(username__iexact=data["username"]).first()
        if user is None or not user.is_active or not user.check_password(data["password"]):
            raise AuthenticationFailed("Invalid credentials.")
        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
```

`apps/users/auth_urls.py` (full file):
```python
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginView, MeView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_auth_login.py tests/test_auth_register.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: JWT login with email or username, refresh, /auth/me"
```

---

### Task 5: PATCH /users/me profile update

**Files:**
- Create: `apps/users/user_urls.py`
- Modify: `apps/users/serializers.py`, `apps/users/views.py`, `config/urls.py`
- Test: `tests/test_users_me.py`

**Interfaces:**
- Consumes: `UserSerializer`, validators from Task 3, `MeView` pattern.
- Produces: `PATCH /api/users/me/` (editable: `username`, `full_name`; same validation as registration; 401 unauthenticated), `apps.users.serializers.UserUpdateSerializer`.

- [ ] **Step 1: Write the failing tests**

`tests/test_users_me.py`:
```python
import pytest

from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

URL = "/api/users/me/"


def test_update_full_name(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.patch(URL, {"full_name": "New Name"})
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.full_name == "New Name"


def test_update_username_taken(api_client):
    UserFactory(username="taken")
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.patch(URL, {"username": "taken"})
    assert response.status_code == 400
    assert "username" in response.json()


def test_update_invalid_username(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.patch(URL, {"username": "bad name!"})
    assert response.status_code == 400


def test_update_requires_auth(api_client):
    response = api_client.patch(URL, {"full_name": "X"})
    assert response.status_code == 401


def test_cannot_change_email_or_verified(api_client):
    user = UserFactory(email="orig@example.com", is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.patch(URL, {"email": "hack@example.com", "is_verified": False})
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.email == "orig@example.com"
    assert user.is_verified is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_users_me.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement**

Append to `apps/users/serializers.py`:
```python
class UserUpdateSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        min_length=3,
        max_length=32,
        required=False,
        validators=[USERNAME_VALIDATOR, UniqueValidator(queryset=User.objects.all())],
    )
    full_name = serializers.CharField(
        min_length=2, max_length=100, required=False, validators=[FULL_NAME_VALIDATOR]
    )

    class Meta:
        model = User
        fields = ["id", "email", "username", "full_name", "is_verified", "created_at"]
        read_only_fields = ["id", "email", "is_verified", "created_at"]
```

Append to `apps/users/views.py`:
```python
from .serializers import UserUpdateSerializer


class UserMeView(generics.UpdateAPIView):
    serializer_class = UserUpdateSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["patch"]

    def get_object(self):
        return self.request.user
```

`apps/users/user_urls.py`:
```python
from django.urls import path

from .views import UserMeView

urlpatterns = [
    path("me/", UserMeView.as_view(), name="users-me"),
]
```

In `config/urls.py` add after the auth include:
```python
    path("api/users/", include("apps.users.user_urls")),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_users_me.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: PATCH /users/me profile update"
```

---

### Task 6: Email verification endpoints

**Files:**
- Modify: `apps/users/views.py`, `apps/users/auth_urls.py`
- Test: `tests/test_email_verification.py`

**Interfaces:**
- Consumes: `EmailVerificationToken`, `send_verification_email`.
- Produces: `GET /api/auth/verify-email/?token=...` (200 sets `is_verified=True`, marks token used; 400 invalid/expired/used), `POST /api/auth/resend-verification/` (JWT; 400 if already verified; issues new token + email).

- [ ] **Step 1: Write the failing tests**

`tests/test_email_verification.py`:
```python
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.users.models import EmailVerificationToken
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

VERIFY_URL = "/api/auth/verify-email/"
RESEND_URL = "/api/auth/resend-verification/"


def test_verify_success(api_client):
    user = UserFactory(is_verified=False)
    token = EmailVerificationToken.issue(user)
    response = api_client.get(VERIFY_URL, {"token": token.token})
    assert response.status_code == 200
    user.refresh_from_db()
    token.refresh_from_db()
    assert user.is_verified is True
    assert token.used_at is not None


def test_verify_unknown_token(api_client):
    response = api_client.get(VERIFY_URL, {"token": "nope"})
    assert response.status_code == 400


def test_verify_expired_token(api_client):
    user = UserFactory(is_verified=False)
    token = EmailVerificationToken.issue(user)
    token.expires_at = timezone.now() - timedelta(minutes=1)
    token.save()
    response = api_client.get(VERIFY_URL, {"token": token.token})
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.is_verified is False


def test_verify_used_token(api_client):
    user = UserFactory(is_verified=False)
    token = EmailVerificationToken.issue(user)
    api_client.get(VERIFY_URL, {"token": token.token})
    response = api_client.get(VERIFY_URL, {"token": token.token})
    assert response.status_code == 400


def test_resend_verification(api_client):
    user = UserFactory(is_verified=False)
    api_client.force_authenticate(user=user)
    response = api_client.post(RESEND_URL)
    assert response.status_code == 200
    assert user.verification_tokens.count() == 1
    assert len(mail.outbox) == 1


def test_resend_already_verified(api_client):
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(RESEND_URL)
    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_email_verification.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement views and routes**

Append to `apps/users/views.py` (add `from django.utils import timezone` and `from drf_spectacular.utils import OpenApiParameter, extend_schema` to imports):
```python
class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[OpenApiParameter(name="token", type=str, required=True)],
        responses={200: None, 400: None},
    )
    def get(self, request):
        token_value = request.query_params.get("token", "")
        token = (
            EmailVerificationToken.objects.select_related("user")
            .filter(token=token_value)
            .first()
        )
        if token is None or not token.is_valid:
            return Response(
                {"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST
            )
        token.used_at = timezone.now()
        token.save(update_fields=["used_at"])
        user = token.user
        if not user.is_verified:
            user.is_verified = True
            user.save(update_fields=["is_verified", "updated_at"])
        return Response({"detail": "Email verified."})


class ResendVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.is_verified:
            return Response(
                {"detail": "Email is already verified."}, status=status.HTTP_400_BAD_REQUEST
            )
        token = EmailVerificationToken.issue(request.user)
        send_verification_email.delay(str(request.user.id), token.token)
        return Response({"detail": "Verification email sent."})
```

Add to `apps/users/auth_urls.py` urlpatterns:
```python
    path("verify-email/", VerifyEmailView.as_view(), name="auth-verify-email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="auth-resend-verification"),
```
(and import `ResendVerificationView, VerifyEmailView` from `.views`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_email_verification.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: email verification and resend endpoints"
```

---

### Task 7: Post model + CRUD endpoints

**Files:**
- Create: `apps/posts/models.py`, `apps/posts/serializers.py`, `apps/posts/views.py`, `apps/posts/urls.py`, `apps/posts/migrations/` (generated)
- Modify: `config/urls.py`, `tests/factories.py`
- Test: `tests/test_posts_crud.py`

**Interfaces:**
- Consumes: `apps.core.permissions.IsVerified`, `IsOwnerOrReadOnly`, `DefaultPagination`, `UserFactory`.
- Produces: `apps.posts.models.Post` (UUID pk, `author` FK related_name `"posts"`, `title`, `content`, timestamps), `GET/POST /api/posts/`, `GET/PATCH/DELETE /api/posts/{id}/`, `apps.posts.serializers.PostSerializer` and `AuthorSerializer` (`id`, `username`), `tests.factories.PostFactory`, `apps.posts.views.PostViewSet` (Task 8 adds filters, Task 9 adds detail comments).

- [ ] **Step 1: Write the failing tests**

Append to `tests/factories.py`:
```python
from apps.posts.models import Post


class PostFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Post

    author = factory.SubFactory(UserFactory)
    title = factory.Sequence(lambda n: f"Post title {n}")
    content = factory.Faker("paragraph")
```

`tests/test_posts_crud.py`:
```python
import pytest

from apps.posts.models import Post
from tests.factories import PostFactory, UserFactory

pytestmark = pytest.mark.django_db

POSTS_URL = "/api/posts/"


def detail_url(post_id):
    return f"/api/posts/{post_id}/"


def test_list_posts_anonymous(api_client):
    PostFactory.create_batch(3)
    response = api_client.get(POSTS_URL)
    assert response.status_code == 200
    assert response.json()["count"] == 3


def test_create_post_verified(api_client):
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(POSTS_URL, {"title": "Hello world", "content": "i love rust"})
    assert response.status_code == 201
    post = Post.objects.get()
    assert post.author == user
    assert response.json()["author"]["username"] == user.username


def test_create_post_unverified_forbidden(api_client):
    user = UserFactory(is_verified=False)
    api_client.force_authenticate(user=user)
    response = api_client.post(POSTS_URL, {"title": "Hello world", "content": "text"})
    assert response.status_code == 403


def test_create_post_anonymous_unauthorized(api_client):
    response = api_client.post(POSTS_URL, {"title": "Hello world", "content": "text"})
    assert response.status_code == 401


def test_create_post_title_too_short(api_client):
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(POSTS_URL, {"title": "Hey", "content": "text"})
    assert response.status_code == 400
    assert "title" in response.json()


def test_retrieve_post(api_client):
    post = PostFactory()
    response = api_client.get(detail_url(post.id))
    assert response.status_code == 200
    assert response.json()["title"] == post.title


def test_patch_own_post(api_client):
    post = PostFactory()
    api_client.force_authenticate(user=post.author)
    response = api_client.patch(detail_url(post.id), {"title": "Updated title"})
    assert response.status_code == 200
    post.refresh_from_db()
    assert post.title == "Updated title"


def test_patch_foreign_post_forbidden(api_client):
    post = PostFactory()
    other = UserFactory(is_verified=True)
    api_client.force_authenticate(user=other)
    response = api_client.patch(detail_url(post.id), {"title": "Hacked title"})
    assert response.status_code == 403


def test_delete_own_post(api_client):
    post = PostFactory()
    api_client.force_authenticate(user=post.author)
    response = api_client.delete(detail_url(post.id))
    assert response.status_code == 204
    assert Post.objects.count() == 0


def test_delete_foreign_post_forbidden(api_client):
    post = PostFactory()
    other = UserFactory(is_verified=True)
    api_client.force_authenticate(user=other)
    response = api_client.delete(detail_url(post.id))
    assert response.status_code == 403
    assert Post.objects.count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_posts_crud.py -v`
Expected: FAIL — `ImportError` (no `apps.posts.models`).

- [ ] **Step 3: Implement model, serializers, viewset**

`apps/posts/models.py`:
```python
import uuid

from django.conf import settings
from django.db import models


class Post(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts"
    )
    title = models.CharField(max_length=255)
    content = models.TextField(max_length=10000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
```

`apps/posts/serializers.py`:
```python
from rest_framework import serializers

from apps.users.models import User

from .models import Post


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username"]


class PostSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    title = serializers.CharField(min_length=5, max_length=255)
    content = serializers.CharField(max_length=10000)

    class Meta:
        model = Post
        fields = ["id", "author", "title", "content", "created_at", "updated_at"]
        read_only_fields = ["id", "author", "created_at", "updated_at"]
```

`apps/posts/views.py`:
```python
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from apps.core.permissions import IsOwnerOrReadOnly, IsVerified

from .models import Post
from .serializers import PostSerializer


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsVerified, IsOwnerOrReadOnly]

    def get_queryset(self):
        return Post.objects.select_related("author").order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
```

`apps/posts/urls.py`:
```python
from rest_framework.routers import DefaultRouter

from .views import PostViewSet

router = DefaultRouter()
router.register("posts", PostViewSet, basename="post")

urlpatterns = [
    *router.urls,
]
```

In `config/urls.py` add:
```python
    path("api/", include("apps.posts.urls")),
```

- [ ] **Step 4: Generate migration, run tests**

Run:
```bash
.venv/bin/python manage.py makemigrations posts
.venv/bin/pytest tests/test_posts_crud.py -v
```
Expected: migration created; all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: Post model with CRUD endpoints and owner/verified permissions"
```

---

### Task 8: Posts pagination, search, date filtering

**Files:**
- Create: `apps/posts/filters.py`
- Modify: `apps/posts/views.py`
- Test: `tests/test_posts_filters.py`

**Interfaces:**
- Consumes: `PostViewSet`, `PostFactory`.
- Produces: `GET /api/posts/?page=&page_size=&search=&date_from=&date_to=` — `search` matches `title`/`content` icontains; `date_from`/`date_to` are ISO datetimes filtering `created_at`. `apps.posts.filters.PostFilter` (reused by feed in Task 11 — no, feed filters over users; feed only paginates. Only posts list uses it).

- [ ] **Step 1: Write the failing tests**

`tests/test_posts_filters.py`:
```python
from datetime import timedelta

import pytest
from django.utils import timezone

from tests.factories import PostFactory

pytestmark = pytest.mark.django_db

POSTS_URL = "/api/posts/"


def test_pagination(api_client):
    PostFactory.create_batch(15)
    response = api_client.get(POSTS_URL, {"page_size": 10})
    body = response.json()
    assert body["count"] == 15
    assert len(body["results"]) == 10
    page2 = api_client.get(POSTS_URL, {"page_size": 10, "page": 2}).json()
    assert len(page2["results"]) == 5


def test_search_title_and_content(api_client):
    PostFactory(title="Rust in production", content="systems language")
    PostFactory(title="Cooking pasta", content="i love rust actually")
    PostFactory(title="Unrelated", content="nothing here")
    body = api_client.get(POSTS_URL, {"search": "rust"}).json()
    assert body["count"] == 2


def test_date_filtering(api_client):
    old = PostFactory()
    old.created_at = timezone.now() - timedelta(days=10)
    old.save(update_fields=["created_at"])
    PostFactory()  # recent
    cutoff = (timezone.now() - timedelta(days=5)).isoformat()
    assert api_client.get(POSTS_URL, {"date_from": cutoff}).json()["count"] == 1
    assert api_client.get(POSTS_URL, {"date_to": cutoff}).json()["count"] == 1
```

Note: `created_at` uses `auto_now_add`, so backdating requires assigning after creation and saving with `update_fields` — Django still overwrites `auto_now_add` only on insert, so this works.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_posts_filters.py -v`
Expected: `test_pagination` PASSES already (pagination is global default); search/date tests FAIL (filters ignored, count == 3 / 2).

- [ ] **Step 3: Implement filterset and wire backends**

`apps/posts/filters.py`:
```python
import django_filters

from .models import Post


class PostFilter(django_filters.FilterSet):
    date_from = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Post
        fields = ["date_from", "date_to"]
```

In `apps/posts/views.py`, add imports and viewset attributes:
```python
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter

from .filters import PostFilter
```
Inside `PostViewSet` add:
```python
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = PostFilter
    search_fields = ["title", "content"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_posts_filters.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: posts search and date-range filtering"
```

---

### Task 9: Comments

**Files:**
- Modify: `apps/posts/models.py`, `apps/posts/serializers.py`, `apps/posts/views.py`, `apps/posts/urls.py`, `tests/factories.py`, `apps/posts/migrations/` (generated)
- Test: `tests/test_comments.py`

**Interfaces:**
- Consumes: `Post`, `IsVerified`, `IsOwnerOrReadOnly`, `PostFactory`, `UserFactory`.
- Produces: `apps.posts.models.Comment` (UUID pk, `post` FK related_name `"comments"`, `author` FK, `content` ≤2000, `created_at`), `GET/POST /api/posts/{post_id}/comments/`, `DELETE /api/posts/{post_id}/comments/{comment_id}/`, `CommentSerializer` (`id, author, content, created_at`), `tests.factories.CommentFactory`. Post detail (`GET /api/posts/{id}/`) now embeds `comments`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/factories.py`:
```python
from apps.posts.models import Comment


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comment

    post = factory.SubFactory(PostFactory)
    author = factory.SubFactory(UserFactory)
    content = factory.Faker("sentence")
```

`tests/test_comments.py`:
```python
import pytest

from apps.posts.models import Comment
from tests.factories import CommentFactory, PostFactory, UserFactory

pytestmark = pytest.mark.django_db


def comments_url(post_id):
    return f"/api/posts/{post_id}/comments/"


def comment_url(post_id, comment_id):
    return f"/api/posts/{post_id}/comments/{comment_id}/"


def test_list_comments(api_client):
    comment = CommentFactory()
    CommentFactory(post=comment.post)
    response = api_client.get(comments_url(comment.post_id))
    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_create_comment_verified(api_client):
    post = PostFactory()
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(comments_url(post.id), {"content": "Nice post!"})
    assert response.status_code == 201
    comment = Comment.objects.get()
    assert comment.author == user
    assert comment.post == post


def test_create_comment_unverified_forbidden(api_client):
    post = PostFactory()
    user = UserFactory(is_verified=False)
    api_client.force_authenticate(user=user)
    response = api_client.post(comments_url(post.id), {"content": "Nope"})
    assert response.status_code == 403


def test_create_comment_missing_post(api_client):
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(
        comments_url("00000000-0000-0000-0000-000000000000"), {"content": "Hi"}
    )
    assert response.status_code == 404


def test_create_comment_too_long(api_client):
    post = PostFactory()
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(comments_url(post.id), {"content": "x" * 2001})
    assert response.status_code == 400


def test_delete_own_comment(api_client):
    comment = CommentFactory()
    api_client.force_authenticate(user=comment.author)
    response = api_client.delete(comment_url(comment.post_id, comment.id))
    assert response.status_code == 204
    assert Comment.objects.count() == 0


def test_delete_foreign_comment_forbidden(api_client):
    comment = CommentFactory()
    other = UserFactory(is_verified=True)
    api_client.force_authenticate(user=other)
    response = api_client.delete(comment_url(comment.post_id, comment.id))
    assert response.status_code == 403


def test_post_detail_includes_comments(api_client):
    comment = CommentFactory(content="First!")
    response = api_client.get(f"/api/posts/{comment.post_id}/")
    assert response.status_code == 200
    body = response.json()
    assert len(body["comments"]) == 1
    assert body["comments"][0]["content"] == "First!"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_comments.py -v`
Expected: FAIL — `ImportError: cannot import name 'Comment'`.

- [ ] **Step 3: Implement model, serializer, views, routes**

Append to `apps/posts/models.py`:
```python
class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments"
    )
    content = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
```

Append to `apps/posts/serializers.py`:
```python
from .models import Comment


class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    content = serializers.CharField(max_length=2000)

    class Meta:
        model = Comment
        fields = ["id", "author", "content", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class PostDetailSerializer(PostSerializer):
    comments = CommentSerializer(many=True, read_only=True)

    class Meta(PostSerializer.Meta):
        fields = PostSerializer.Meta.fields + ["comments"]
```

In `apps/posts/views.py` add imports:
```python
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Comment
from .serializers import CommentSerializer, PostDetailSerializer
```

In `PostViewSet` add serializer switching and comment prefetch for retrieve:
```python
    def get_serializer_class(self):
        if self.action == "retrieve":
            return PostDetailSerializer
        return PostSerializer

    def get_queryset(self):
        qs = Post.objects.select_related("author").order_by("-created_at")
        if self.action == "retrieve":
            qs = qs.prefetch_related("comments__author")
        return qs
```
(replace the existing `get_queryset` with this version).

Append comment views:
```python
class CommentListCreateView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsVerified]

    def get_queryset(self):
        return (
            Comment.objects.filter(post_id=self.kwargs["post_id"])
            .select_related("author")
            .order_by("created_at")
        )

    def perform_create(self, serializer):
        post = get_object_or_404(Post, pk=self.kwargs["post_id"])
        serializer.save(author=self.request.user, post=post)


class CommentDeleteView(generics.DestroyAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    lookup_url_kwarg = "comment_id"

    def get_queryset(self):
        return Comment.objects.filter(post_id=self.kwargs["post_id"])
```

`apps/posts/urls.py` (full file):
```python
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CommentDeleteView, CommentListCreateView, PostViewSet

router = DefaultRouter()
router.register("posts", PostViewSet, basename="post")

urlpatterns = [
    path(
        "posts/<uuid:post_id>/comments/",
        CommentListCreateView.as_view(),
        name="post-comments",
    ),
    path(
        "posts/<uuid:post_id>/comments/<uuid:comment_id>/",
        CommentDeleteView.as_view(),
        name="post-comment-delete",
    ),
    *router.urls,
]
```

- [ ] **Step 4: Generate migration, run tests**

Run:
```bash
.venv/bin/python manage.py makemigrations posts
.venv/bin/pytest tests/test_comments.py tests/test_posts_crud.py -v
```
Expected: migration created; all PASS (posts CRUD unaffected).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: comments with nested routes and post detail embedding"
```

---

### Task 10: Likes

**Files:**
- Modify: `apps/posts/models.py`, `apps/posts/views.py`, `apps/posts/urls.py`, `apps/posts/migrations/` (generated)
- Test: `tests/test_likes.py`

**Interfaces:**
- Consumes: `Post`, `PostFactory`, `UserFactory`.
- Produces: `apps.posts.models.Like` (UUID pk, `user` FK related_name `"likes"`, `post` FK related_name `"likes"`, unique `(user, post)`), `POST /api/posts/{post_id}/like/` (201; 403 own post; 400 duplicate), `DELETE /api/posts/{post_id}/like/` (204; 404 if absent). Feed (Task 11) reads `post.likes` with `like.user_id`.

- [ ] **Step 1: Write the failing tests**

`tests/test_likes.py`:
```python
import pytest
from django.db import IntegrityError

from apps.posts.models import Like
from tests.factories import PostFactory, UserFactory

pytestmark = pytest.mark.django_db


def like_url(post_id):
    return f"/api/posts/{post_id}/like/"


def test_like_post(api_client):
    post = PostFactory()
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.post(like_url(post.id))
    assert response.status_code == 201
    assert Like.objects.filter(user=user, post=post).exists()


def test_unverified_user_can_like(api_client):
    post = PostFactory()
    user = UserFactory(is_verified=False)
    api_client.force_authenticate(user=user)
    response = api_client.post(like_url(post.id))
    assert response.status_code == 201


def test_cannot_like_own_post(api_client):
    post = PostFactory()
    api_client.force_authenticate(user=post.author)
    response = api_client.post(like_url(post.id))
    assert response.status_code == 403
    assert Like.objects.count() == 0


def test_cannot_like_twice(api_client):
    post = PostFactory()
    user = UserFactory()
    api_client.force_authenticate(user=user)
    api_client.post(like_url(post.id))
    response = api_client.post(like_url(post.id))
    assert response.status_code == 400
    assert Like.objects.count() == 1


def test_like_requires_auth(api_client):
    post = PostFactory()
    response = api_client.post(like_url(post.id))
    assert response.status_code == 401


def test_like_missing_post(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.post(like_url("00000000-0000-0000-0000-000000000000"))
    assert response.status_code == 404


def test_unlike(api_client):
    post = PostFactory()
    user = UserFactory()
    api_client.force_authenticate(user=user)
    api_client.post(like_url(post.id))
    response = api_client.delete(like_url(post.id))
    assert response.status_code == 204
    assert Like.objects.count() == 0


def test_unlike_without_like_returns_404(api_client):
    post = PostFactory()
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.delete(like_url(post.id))
    assert response.status_code == 404


def test_db_unique_constraint(api_client):
    post = PostFactory()
    user = UserFactory()
    Like.objects.create(user=user, post=post)
    with pytest.raises(IntegrityError):
        Like.objects.create(user=user, post=post)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_likes.py -v`
Expected: FAIL — `ImportError: cannot import name 'Like'`.

- [ ] **Step 3: Implement model and view**

Append to `apps/posts/models.py`:
```python
class Like(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="likes"
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "post"], name="unique_user_post_like")
        ]
```

Append to `apps/posts/views.py` (add `from rest_framework import status`, `from rest_framework.response import Response`, `from rest_framework.views import APIView`, `from .models import Like` to imports):
```python
class LikeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):
        post = get_object_or_404(Post, pk=post_id)
        if post.author_id == request.user.id:
            return Response(
                {"detail": "You cannot like your own post."}, status=status.HTTP_403_FORBIDDEN
            )
        _, created = Like.objects.get_or_create(user=request.user, post=post)
        if not created:
            return Response(
                {"detail": "You have already liked this post."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": "Liked."}, status=status.HTTP_201_CREATED)

    def delete(self, request, post_id):
        deleted, _ = Like.objects.filter(user=request.user, post_id=post_id).delete()
        if not deleted:
            return Response({"detail": "Like not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
```

Add route in `apps/posts/urls.py` before `*router.urls`:
```python
    path("posts/<uuid:post_id>/like/", LikeView.as_view(), name="post-like"),
```
(and import `LikeView`).

- [ ] **Step 4: Generate migration, run tests**

Run:
```bash
.venv/bin/python manage.py makemigrations posts
.venv/bin/pytest tests/test_likes.py -v
```
Expected: migration created; all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: likes with no-self-like and unique constraint rules"
```

---

### Task 11: Feed endpoint

**Files:**
- Modify: `apps/posts/serializers.py`, `apps/posts/views.py`, `apps/posts/urls.py`
- Test: `tests/test_feed.py`

**Interfaces:**
- Consumes: `User`, `Post.likes` (related manager from Task 10), `DefaultPagination`.
- Produces: `GET /api/feed/` — paginated over users who have ≥1 post, each item `{"username": str, "posts": [{"id", "title", "content", "likes": [user_uuid_str, ...]}]}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_feed.py`:
```python
import pytest

from apps.posts.models import Like
from tests.factories import PostFactory, UserFactory

pytestmark = pytest.mark.django_db

FEED_URL = "/api/feed/"


def test_feed_structure(api_client):
    author = UserFactory(username="kamran")
    post = PostFactory(author=author, title="Uzbekistan post", content="tashkent")
    liker = UserFactory()
    Like.objects.create(user=liker, post=post)

    response = api_client.get(FEED_URL)
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    entry = results[0]
    assert entry["username"] == "kamran"
    assert len(entry["posts"]) == 1
    assert entry["posts"][0]["title"] == "Uzbekistan post"
    assert entry["posts"][0]["likes"] == [str(liker.id)]


def test_feed_excludes_users_without_posts(api_client):
    UserFactory()
    PostFactory()
    results = api_client.get(FEED_URL).json()["results"]
    assert len(results) == 1


def test_feed_pagination(api_client):
    for _ in range(12):
        PostFactory()
    body = api_client.get(FEED_URL, {"page_size": 10}).json()
    assert body["count"] == 12
    assert len(body["results"]) == 10


def test_feed_query_count(api_client, django_assert_max_num_queries):
    for _ in range(5):
        post = PostFactory()
        Like.objects.create(user=UserFactory(), post=post)
    with django_assert_max_num_queries(4):
        api_client.get(FEED_URL)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_feed.py -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement feed serializers and view**

Append to `apps/posts/serializers.py`:
```python
class FeedPostSerializer(serializers.ModelSerializer):
    likes = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = ["id", "title", "content", "likes"]

    def get_likes(self, obj):
        return [str(like.user_id) for like in obj.likes.all()]


class FeedUserSerializer(serializers.ModelSerializer):
    posts = FeedPostSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ["username", "posts"]
```

Append to `apps/posts/views.py` (add `from django.db.models import Prefetch` and `from apps.users.models import User` and `from rest_framework.permissions import AllowAny` and `from .serializers import FeedUserSerializer` to imports):
```python
class FeedView(generics.ListAPIView):
    serializer_class = FeedUserSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return (
            User.objects.filter(posts__isnull=False)
            .distinct()
            .order_by("username")
            .prefetch_related(
                Prefetch(
                    "posts",
                    queryset=Post.objects.order_by("-created_at").prefetch_related("likes"),
                )
            )
        )
```

Add route in `apps/posts/urls.py`:
```python
    path("feed/", FeedView.as_view(), name="feed"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_feed.py -v`
Expected: all PASS (query count: 1 count + 1 users + 1 posts prefetch + 1 likes prefetch = 4).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: /feed endpoint grouping posts and likes by user"
```

---

### Task 12: Cleanup background tasks + beat + management command

**Files:**
- Create: `apps/posts/tasks.py`, `apps/users/management/__init__.py`, `apps/users/management/commands/__init__.py`, `apps/users/management/commands/cleanup_unverified_users.py`
- Modify: `apps/users/tasks.py`
- Test: `tests/test_cleanup.py`

**Interfaces:**
- Consumes: `User`, `Post`, settings `UNVERIFIED_USER_TTL_HOURS`, `POST_TTL_DAYS`; beat schedule entries already declared in `config/settings.py` (Task 1) reference these task paths.
- Produces: `apps.users.tasks.cleanup_unverified_users() -> int` (deleted count), `apps.posts.tasks.cleanup_old_posts() -> int`, management command `python manage.py cleanup_unverified_users`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cleanup.py`:
```python
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.posts.models import Post
from apps.posts.tasks import cleanup_old_posts
from apps.users.models import User
from apps.users.tasks import cleanup_unverified_users
from tests.factories import PostFactory, UserFactory

pytestmark = pytest.mark.django_db


def backdate_user(user, hours):
    User.objects.filter(pk=user.pk).update(
        created_at=timezone.now() - timedelta(hours=hours)
    )


def test_cleanup_deletes_stale_unverified():
    stale = UserFactory(is_verified=False)
    backdate_user(stale, hours=48)
    deleted = cleanup_unverified_users()
    assert deleted == 1
    assert not User.objects.filter(pk=stale.pk).exists()


def test_cleanup_keeps_fresh_unverified():
    UserFactory(is_verified=False)
    assert cleanup_unverified_users() == 0
    assert User.objects.count() == 1


def test_cleanup_keeps_verified():
    old_verified = UserFactory(is_verified=True)
    backdate_user(old_verified, hours=48)
    assert cleanup_unverified_users() == 0


def test_cleanup_keeps_staff():
    staff = UserFactory(is_verified=False, is_staff=True)
    backdate_user(staff, hours=48)
    assert cleanup_unverified_users() == 0


def test_cleanup_management_command():
    stale = UserFactory(is_verified=False)
    backdate_user(stale, hours=48)
    call_command("cleanup_unverified_users")
    assert not User.objects.filter(pk=stale.pk).exists()


def test_cleanup_old_posts_disabled_by_default(settings):
    settings.POST_TTL_DAYS = 0
    post = PostFactory()
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(days=365))
    assert cleanup_old_posts() == 0
    assert Post.objects.count() == 1


def test_cleanup_old_posts_when_enabled(settings):
    settings.POST_TTL_DAYS = 30
    old = PostFactory()
    Post.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))
    PostFactory()  # fresh
    assert cleanup_old_posts() == 1
    assert Post.objects.count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cleanup.py -v`
Expected: FAIL — `ImportError` (`cleanup_unverified_users`, `apps.posts.tasks` missing).

- [ ] **Step 3: Implement tasks and command**

Append to `apps/users/tasks.py` (add `from datetime import timedelta` and `from django.utils import timezone` to imports). Note: `queryset.delete()` returns `(total_rows, per_model_dict)` where `total_rows` includes cascaded `EmailVerificationToken` rows, so count users explicitly before deleting:

```python
@shared_task
def cleanup_unverified_users():
    cutoff = timezone.now() - timedelta(hours=settings.UNVERIFIED_USER_TTL_HOURS)
    stale = User.objects.filter(is_verified=False, is_staff=False, created_at__lt=cutoff)
    count = stale.count()
    stale.delete()
    return count
```

`apps/posts/tasks.py`:
```python
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Post


@shared_task
def cleanup_old_posts():
    days = settings.POST_TTL_DAYS
    if not days:
        return 0
    cutoff = timezone.now() - timedelta(days=days)
    stale = Post.objects.filter(created_at__lt=cutoff)
    count = stale.count()
    stale.delete()
    return count
```

`apps/users/management/commands/cleanup_unverified_users.py` (create empty `__init__.py` files in `management/` and `management/commands/`):
```python
from django.core.management.base import BaseCommand

from apps.users.tasks import cleanup_unverified_users


class Command(BaseCommand):
    help = "Delete unverified users older than UNVERIFIED_USER_TTL_HOURS."

    def handle(self, *args, **options):
        deleted = cleanup_unverified_users()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} unverified user(s)."))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cleanup.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: periodic cleanup tasks for unverified users and old posts"
```

---

### Task 13: Login rate limiting + failed-attempt lockout

**Files:**
- Create: `apps/users/lockout.py`
- Modify: `apps/users/views.py`
- Test: `tests/test_login_lockout.py`

**Interfaces:**
- Consumes: `LoginView` (Task 4), Django cache, settings `LOGIN_MAX_FAILURES` / `LOGIN_LOCKOUT_MINUTES`.
- Produces: `apps.users.lockout` module with `is_locked(identifier) -> bool`, `register_failure(identifier) -> None`, `reset(identifier) -> None`; `LoginView` gains `throttle_classes=[ScopedRateThrottle]`, `throttle_scope="login"`, and returns 429 while locked.

- [ ] **Step 1: Write the failing tests**

`tests/test_login_lockout.py`:
```python
import pytest
from django.core.cache import cache

from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user():
    return UserFactory(email="kam@example.com", username="kamran")


def fail_login(api_client, n):
    for _ in range(n):
        api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "wrong"})


def test_lockout_after_max_failures(api_client, user, settings):
    settings.LOGIN_MAX_FAILURES = 3
    fail_login(api_client, 3)
    response = api_client.post(
        LOGIN_URL, {"email": "kam@example.com", "password": "password123"}
    )
    assert response.status_code == 429


def test_no_lockout_below_threshold(api_client, user, settings):
    settings.LOGIN_MAX_FAILURES = 3
    fail_login(api_client, 2)
    response = api_client.post(
        LOGIN_URL, {"email": "kam@example.com", "password": "password123"}
    )
    assert response.status_code == 200


def test_success_resets_counter(api_client, user, settings):
    settings.LOGIN_MAX_FAILURES = 3
    fail_login(api_client, 2)
    api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "password123"})
    fail_login(api_client, 2)
    response = api_client.post(
        LOGIN_URL, {"email": "kam@example.com", "password": "password123"}
    )
    assert response.status_code == 200


def test_lockout_scoped_to_identifier(api_client, user, settings):
    settings.LOGIN_MAX_FAILURES = 3
    other = UserFactory(email="other@example.com")
    fail_login(api_client, 3)
    response = api_client.post(
        LOGIN_URL, {"email": "other@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    assert other.email == "other@example.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_login_lockout.py -v`
Expected: `test_lockout_after_max_failures` FAILS (200 instead of 429); others may pass incidentally.

- [ ] **Step 3: Implement lockout module and wire into LoginView**

`apps/users/lockout.py`:
```python
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
```

In `apps/users/views.py`, add imports:
```python
from rest_framework.throttling import ScopedRateThrottle

from . import lockout
```

Replace `LoginView.post` with (full class):
```python
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        identifier = data.get("email") or data.get("username")
        if lockout.is_locked(identifier):
            return Response(
                {"detail": "Too many failed attempts. Try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if data.get("email"):
            user = User.objects.filter(email__iexact=data["email"]).first()
        else:
            user = User.objects.filter(username__iexact=data["username"]).first()
        if user is None or not user.is_active or not user.check_password(data["password"]):
            lockout.register_failure(identifier)
            raise AuthenticationFailed("Invalid credentials.")
        lockout.reset(identifier)
        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})
```
(`status` is already imported in this file from Task 3's `from rest_framework import generics, status`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_login_lockout.py tests/test_auth_login.py -v`
Expected: all PASS (login flow unchanged for valid credentials).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: login throttling and failed-attempt lockout"
```

---

### Task 14: Docker packaging + README

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker/entrypoint.sh`, `README.md`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: everything built so far; `config.wsgi:application`; `manage.py migrate`.
- Produces: `docker compose up --build` brings up db, redis, web (gunicorn on :8000, auto-migrates), celery_worker, celery_beat. Swagger reachable at `http://localhost:8000/api/docs/`.

- [ ] **Step 1: Write Dockerfile, entrypoint, dockerignore**

`Dockerfile` (multi-stage):
```dockerfile
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim

RUN useradd --create-home appuser
WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY . .
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
ENTRYPOINT ["./docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
```

`docker/entrypoint.sh` (make executable: `chmod +x docker/entrypoint.sh`):
```bash
#!/bin/sh
set -e

if [ "$1" = "gunicorn" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
```

`.dockerignore`:
```
.venv
.git
__pycache__
*.pyc
.env
.pytest_cache
.ruff_cache
docs
```

- [ ] **Step 2: Extend docker-compose with app services**

`docker-compose.yml` (full file):
```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-social}
      POSTGRES_USER: ${POSTGRES_USER:-social}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-social}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-social}"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  web:
    build: .
    env_file: .env
    environment:
      POSTGRES_HOST: db
      REDIS_URL: redis://redis:6379/0
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  celery_worker:
    build: .
    command: celery -A config worker --loglevel=info
    env_file: .env
    environment:
      POSTGRES_HOST: db
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  celery_beat:
    build: .
    command: celery -A config beat --loglevel=info
    env_file: .env
    environment:
      POSTGRES_HOST: db
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  pgdata:
```

- [ ] **Step 3: Write README.md**

`README.md` — must contain these sections (write real content, not placeholders):

```markdown
# Mini Social Network API

Django REST backend: users, posts, comments, likes, JWT auth, email
verification, background cleanup via Celery + Redis.

## Quick start

    cp .env.example .env      # fill EMAIL_HOST_USER / EMAIL_HOST_PASSWORD for real emails
    docker compose up --build

- API: http://localhost:8000/api/
- Swagger UI: http://localhost:8000/api/docs/ (use "Authorize" with `Bearer <access>`)
- ReDoc: http://localhost:8000/api/redoc/

Without Gmail credentials the app logs verification emails to the web
container console instead of sending them.

## Example requests

    # register
    curl -X POST localhost:8000/api/auth/register/ -H 'Content-Type: application/json' \
      -d '{"email":"a@example.com","username":"alice","full_name":"Alice A","password":"strongPass123"}'

    # login (email or username)
    curl -X POST localhost:8000/api/auth/login/ -H 'Content-Type: application/json' \
      -d '{"email":"a@example.com","password":"strongPass123"}'

    # verify email (token from the email / console log)
    curl 'localhost:8000/api/auth/verify-email/?token=<token>'

    # create a post
    curl -X POST localhost:8000/api/posts/ -H "Authorization: Bearer <access>" \
      -H 'Content-Type: application/json' -d '{"title":"Hello world","content":"first post"}'

    # feed
    curl 'localhost:8000/api/feed/?page=1&page_size=10'

    # posts with search + date filter
    curl 'localhost:8000/api/posts/?search=rust&date_from=2026-01-01T00:00:00Z'

## Endpoints overview

| Method | Path | Auth |
|---|---|---|
| POST | /api/auth/register/ | — |
| POST | /api/auth/login/ | — (throttled) |
| POST | /api/auth/refresh/ | — |
| GET | /api/auth/me/ | JWT |
| GET | /api/auth/verify-email/?token= | — |
| POST | /api/auth/resend-verification/ | JWT |
| PATCH | /api/users/me/ | JWT |
| GET | /api/posts/ | — |
| POST | /api/posts/ | JWT + verified |
| GET | /api/posts/{id}/ | — |
| PATCH/DELETE | /api/posts/{id}/ | JWT, author only |
| GET | /api/posts/{id}/comments/ | — |
| POST | /api/posts/{id}/comments/ | JWT + verified |
| DELETE | /api/posts/{id}/comments/{comment_id}/ | JWT, author only |
| POST/DELETE | /api/posts/{id}/like/ | JWT |
| GET | /api/feed/ | — |
| GET | /api/docs/, /api/redoc/, /api/schema/ | — |

## Project structure

    config/       # settings, urls, celery app
    apps/core/    # shared pagination + permission classes
    apps/users/   # User model, JWT auth, email verification, cleanup task
    apps/posts/   # posts, comments, likes, feed, post TTL task
    tests/        # pytest suite

## Background jobs

- `cleanup_unverified_users` — hourly (Celery beat): deletes unverified users
  older than `UNVERIFIED_USER_TTL_HOURS` (default 24). Manual run:
  `docker compose exec web python manage.py cleanup_unverified_users`
- `cleanup_old_posts` — daily: deletes posts older than `POST_TTL_DAYS`
  (default 0 = disabled).

## Rate limiting

Login is throttled (`LOGIN_THROTTLE_RATE`, default 10/min) and locks an
account identifier for `LOGIN_LOCKOUT_MINUTES` after `LOGIN_MAX_FAILURES`
consecutive failures.

## Running tests locally

    docker compose up -d db redis
    python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
    .venv/bin/pytest
```

Fill in the endpoints table with all routes: register, login, refresh, me, verify-email, resend-verification, users/me, posts CRUD, comments, like/unlike, feed, schema/docs/redoc.

- [ ] **Step 4: Build and verify the full stack**

Run:
```bash
docker compose up --build -d
sleep 15
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/posts/
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/docs/
docker compose ps
```
Expected: both curls return `200`; `docker compose ps` shows web, celery_worker, celery_beat, db, redis all running (worker/beat logs show connected to redis).

Then smoke-test registration end-to-end:
```bash
curl -s -X POST localhost:8000/api/auth/register/ -H 'Content-Type: application/json' \
  -d '{"email":"smoke@example.com","username":"smoketest","full_name":"Smoke Test","password":"strongPass123"}'
docker compose logs celery_worker | grep -i "send_verification_email"
```
Expected: 201 response; worker log shows the task succeeded (email printed to console if no SMTP creds in `.env`).

- [ ] **Step 5: Verify tests still pass locally, then commit**

Run: `.venv/bin/pytest`
Expected: full suite PASS.

```bash
git add -A
git commit -m "feat: dockerize app with celery worker/beat and add README"
```

---

### Task 15: CI + pre-commit

**Files:**
- Create: `.github/workflows/ci.yml`, `.pre-commit-config.yaml`

**Interfaces:**
- Consumes: `requirements-dev.txt`, pytest suite, ruff config.
- Produces: GitHub Actions workflow running lint + tests on push/PR; pre-commit config with ruff lint + format.

- [ ] **Step 1: Write the workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: social
          POSTGRES_USER: social
          POSTGRES_PASSWORD: social
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U social"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Lint
        run: |
          ruff check .
          ruff format --check .

      - name: Run tests
        run: pytest -v
```

- [ ] **Step 2: Write pre-commit config**

`.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

- [ ] **Step 3: Verify lint passes exactly as CI will run it**

Run:
```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q
```
Expected: no lint errors, no format diffs, full suite PASS. Fix any formatting drift with `.venv/bin/ruff format .` before committing.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "ci: GitHub Actions workflow and pre-commit hooks"
```

---

## Final Verification (after all tasks)

- [ ] `.venv/bin/pytest -v` — full suite green.
- [ ] `.venv/bin/ruff check . && .venv/bin/ruff format --check .` — clean.
- [ ] `docker compose up --build` — all 5 services healthy; Swagger at `/api/docs/`.
- [ ] Manual walk-through in Swagger: register → check email/console for token → verify → login → create post → comment → like from second account → feed shows structure.
- [ ] Spec check: every endpoint in the spec table exists; validation limits enforced; unverified user blocked from posting but able to like.
