from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from django.core import mail
from django.core.cache import cache
from rest_framework.throttling import ScopedRateThrottle

from apps.users.models import EmailVerificationToken, User
from apps.users.tasks import send_verification_email
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


def test_send_verification_email_retries_on_failure():
    user = UserFactory(is_verified=False)
    token = EmailVerificationToken.issue(user)
    with patch("apps.users.tasks.send_mail", side_effect=OSError("smtp down")):
        with pytest.raises(Retry):
            send_verification_email.apply(args=[str(user.id), token.token], throw=True)


def test_register_throttled(api_client):
    cache.clear()
    with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"register": "2/hour"}):
        for i in range(2):
            api_client.post(
                REGISTER_URL,
                {
                    "email": f"tr{i}@example.com",
                    "username": f"throttled{i}",
                    "full_name": "Throttle Test",
                    "password": "strongPass123",
                },
            )
        response = api_client.post(
            REGISTER_URL, {**PAYLOAD, "email": "tr9@example.com", "username": "throttled9"}
        )
    cache.clear()
    assert response.status_code == 429
