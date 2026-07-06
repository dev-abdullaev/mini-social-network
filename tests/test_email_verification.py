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
