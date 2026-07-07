import pytest

from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"
LOGOUT_URL = "/api/auth/logout/"
REFRESH_URL = "/api/auth/refresh/"


@pytest.fixture
def user():
    return UserFactory(email="kam@example.com", username="kamran")


def _login(api_client):
    response = api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "password123"})
    return response.json()


def test_logout_with_valid_refresh_blacklists_it(api_client, user):
    tokens = _login(api_client)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    response = api_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]})
    assert response.status_code == 205

    # blacklisted refresh can no longer be used
    api_client.credentials()
    refresh_response = api_client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
    assert refresh_response.status_code == 401


def test_logout_without_refresh_returns_400(api_client, user):
    tokens = _login(api_client)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    response = api_client.post(LOGOUT_URL, {})
    assert response.status_code == 400


def test_logout_with_garbage_refresh_returns_400(api_client, user):
    tokens = _login(api_client)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    response = api_client.post(LOGOUT_URL, {"refresh": "not-a-token"})
    assert response.status_code == 400


def test_logout_without_auth_returns_401(api_client, user):
    tokens = _login(api_client)

    response = api_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]})
    assert response.status_code == 401


def test_refresh_rotation_blacklists_old_refresh_and_returns_new_one(api_client, user):
    tokens = _login(api_client)

    response = api_client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
    assert response.status_code == 200
    data = response.json()
    assert "access" in data
    assert "refresh" in data
    assert data["refresh"] != tokens["refresh"]

    # old refresh token was rotated + blacklisted, reusing it must fail
    reuse_response = api_client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
    assert reuse_response.status_code == 401

    # the new refresh token still works
    new_refresh_response = api_client.post(REFRESH_URL, {"refresh": data["refresh"]})
    assert new_refresh_response.status_code == 200
