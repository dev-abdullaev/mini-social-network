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
