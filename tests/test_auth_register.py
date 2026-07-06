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
