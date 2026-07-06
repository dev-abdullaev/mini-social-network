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
