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
