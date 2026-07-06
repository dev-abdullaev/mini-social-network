import pytest

from apps.posts.models import Post
from tests.factories import PostFactory, UserFactory

pytestmark = pytest.mark.django_db

POSTS_URL = "/api/posts/"


def detail_url(post_id):
    return f"/api/posts/{post_id}/"


def test_list_posts_anonymous(api_client):
    PostFactory.create_batch(3)
    response = api_client.get(POSTS_URL)
    assert response.status_code == 200
    assert response.json()["count"] == 3


def test_create_post_verified(api_client):
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(POSTS_URL, {"title": "Hello world", "content": "i love rust"})
    assert response.status_code == 201
    post = Post.objects.get()
    assert post.author == user
    assert response.json()["author"]["username"] == user.username


def test_create_post_unverified_forbidden(api_client):
    user = UserFactory(is_verified=False)
    api_client.force_authenticate(user=user)
    response = api_client.post(POSTS_URL, {"title": "Hello world", "content": "text"})
    assert response.status_code == 403


def test_create_post_anonymous_unauthorized(api_client):
    response = api_client.post(POSTS_URL, {"title": "Hello world", "content": "text"})
    assert response.status_code == 401


def test_create_post_title_too_short(api_client):
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(POSTS_URL, {"title": "Hey", "content": "text"})
    assert response.status_code == 400
    assert "title" in response.json()


def test_retrieve_post(api_client):
    post = PostFactory()
    response = api_client.get(detail_url(post.id))
    assert response.status_code == 200
    assert response.json()["title"] == post.title


def test_patch_own_post(api_client):
    post = PostFactory()
    api_client.force_authenticate(user=post.author)
    response = api_client.patch(detail_url(post.id), {"title": "Updated title"})
    assert response.status_code == 200
    post.refresh_from_db()
    assert post.title == "Updated title"


def test_patch_foreign_post_forbidden(api_client):
    post = PostFactory()
    other = UserFactory(is_verified=True)
    api_client.force_authenticate(user=other)
    response = api_client.patch(detail_url(post.id), {"title": "Hacked title"})
    assert response.status_code == 403


def test_delete_own_post(api_client):
    post = PostFactory()
    api_client.force_authenticate(user=post.author)
    response = api_client.delete(detail_url(post.id))
    assert response.status_code == 204
    assert Post.objects.count() == 0


def test_delete_foreign_post_forbidden(api_client):
    post = PostFactory()
    other = UserFactory(is_verified=True)
    api_client.force_authenticate(user=other)
    response = api_client.delete(detail_url(post.id))
    assert response.status_code == 403
    assert Post.objects.count() == 1
