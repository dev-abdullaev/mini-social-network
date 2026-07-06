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
