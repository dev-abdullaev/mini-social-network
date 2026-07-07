from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.users.models import PasswordResetToken
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

RESET_URL = "/api/auth/password-reset/"
CONFIRM_URL = "/api/auth/password-reset/confirm/"
LOGIN_URL = "/api/auth/login/"


def test_request_with_existing_email(api_client):
    user = UserFactory(email="kam@example.com")
    response = api_client.post(RESET_URL, {"email": "kam@example.com"})
    assert response.status_code == 200
    assert response.json() == {"detail": "If that email exists, a reset link has been sent."}
    assert len(mail.outbox) == 1
    token = PasswordResetToken.objects.get(user=user)
    assert token.token in mail.outbox[0].body


def test_request_with_unknown_email(api_client):
    response = api_client.post(RESET_URL, {"email": "nobody@example.com"})
    assert response.status_code == 200
    assert response.json() == {"detail": "If that email exists, a reset link has been sent."}
    assert len(mail.outbox) == 0
    assert PasswordResetToken.objects.count() == 0


def test_confirm_success(api_client):
    user = UserFactory(email="kam@example.com")
    token = PasswordResetToken.issue(user)
    response = api_client.post(CONFIRM_URL, {"token": token.token, "new_password": "newpass456"})
    assert response.status_code == 200
    user.refresh_from_db()
    token.refresh_from_db()
    assert user.check_password("newpass456")
    assert token.used_at is not None

    old_login = api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "password123"})
    assert old_login.status_code == 401

    new_login = api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "newpass456"})
    assert new_login.status_code == 200


def test_confirm_unknown_token(api_client):
    response = api_client.post(CONFIRM_URL, {"token": "nope", "new_password": "newpass456"})
    assert response.status_code == 400


def test_confirm_expired_token(api_client):
    user = UserFactory(email="kam@example.com")
    token = PasswordResetToken.issue(user)
    token.expires_at = timezone.now() - timedelta(minutes=1)
    token.save()
    response = api_client.post(CONFIRM_URL, {"token": token.token, "new_password": "newpass456"})
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password("password123")


def test_confirm_used_token(api_client):
    user = UserFactory(email="kam@example.com")
    token = PasswordResetToken.issue(user)
    token.used_at = timezone.now()
    token.save()
    response = api_client.post(CONFIRM_URL, {"token": token.token, "new_password": "newpass456"})
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password("password123")


def test_confirm_weak_password(api_client):
    user = UserFactory(email="kam@example.com")
    token = PasswordResetToken.issue(user)
    response = api_client.post(CONFIRM_URL, {"token": token.token, "new_password": "123"})
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password("password123")


def test_reset_revokes_existing_sessions(api_client):
    user = UserFactory(email="s@example.com")
    # login to get a refresh token
    tokens = api_client.post(
        LOGIN_URL, {"email": "s@example.com", "password": "password123"}
    ).json()
    token = PasswordResetToken.issue(user)
    resp = api_client.post(
        CONFIRM_URL,
        {"token": token.token, "new_password": "brandNewPass99"},
    )
    assert resp.status_code == 200
    # the old refresh must now be blacklisted
    r = api_client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]})
    assert r.status_code == 401


def test_confirm_invalidates_other_unused_tokens(api_client):
    user = UserFactory(email="kam2@example.com")
    stale_token = PasswordResetToken.issue(user)
    active_token = PasswordResetToken.issue(user)
    response = api_client.post(
        CONFIRM_URL, {"token": active_token.token, "new_password": "newpass456"}
    )
    assert response.status_code == 200
    stale_token.refresh_from_db()
    assert stale_token.used_at is not None


def test_confirm_inactive_user(api_client):
    user = UserFactory(email="inactive@example.com", is_active=False)
    token = PasswordResetToken.issue(user)
    response = api_client.post(CONFIRM_URL, {"token": token.token, "new_password": "newpass456"})
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password("password123")
