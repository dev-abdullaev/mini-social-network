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
    response = api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "password123"})
    assert response.status_code == 429


def test_no_lockout_below_threshold(api_client, user, settings):
    settings.LOGIN_MAX_FAILURES = 3
    fail_login(api_client, 2)
    response = api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "password123"})
    assert response.status_code == 200


def test_success_resets_counter(api_client, user, settings):
    settings.LOGIN_MAX_FAILURES = 3
    fail_login(api_client, 2)
    api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "password123"})
    fail_login(api_client, 2)
    response = api_client.post(LOGIN_URL, {"email": "kam@example.com", "password": "password123"})
    assert response.status_code == 200


def test_lockout_scoped_to_identifier(api_client, user, settings):
    settings.LOGIN_MAX_FAILURES = 3
    other = UserFactory(email="other@example.com")
    fail_login(api_client, 3)
    response = api_client.post(LOGIN_URL, {"email": "other@example.com", "password": "password123"})
    assert response.status_code == 200
    assert other.email == "other@example.com"
