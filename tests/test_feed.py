import pytest

from apps.posts.models import Like
from tests.factories import PostFactory, UserFactory

pytestmark = pytest.mark.django_db

FEED_URL = "/api/feed/"


def test_feed_structure(api_client):
    author = UserFactory(username="kamran")
    post = PostFactory(author=author, title="Uzbekistan post", content="tashkent")
    liker = UserFactory()
    Like.objects.create(user=liker, post=post)

    response = api_client.get(FEED_URL)
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    entry = results[0]
    assert entry["username"] == "kamran"
    assert len(entry["posts"]) == 1
    assert entry["posts"][0]["title"] == "Uzbekistan post"
    assert entry["posts"][0]["likes"] == [str(liker.id)]


def test_feed_excludes_users_without_posts(api_client):
    UserFactory()
    PostFactory()
    results = api_client.get(FEED_URL).json()["results"]
    assert len(results) == 1


def test_feed_pagination(api_client):
    for _ in range(12):
        PostFactory()
    body = api_client.get(FEED_URL, {"page_size": 10}).json()
    assert body["count"] == 12
    assert len(body["results"]) == 10


def test_feed_query_count(api_client, django_assert_max_num_queries):
    for _ in range(5):
        post = PostFactory()
        Like.objects.create(user=UserFactory(), post=post)
    with django_assert_max_num_queries(4):
        api_client.get(FEED_URL)
