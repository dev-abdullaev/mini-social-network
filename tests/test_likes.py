import pytest
from django.db import IntegrityError

from apps.posts.models import Like
from tests.factories import PostFactory, UserFactory

pytestmark = pytest.mark.django_db


def like_url(post_id):
    return f"/api/posts/{post_id}/like/"


def test_like_post(api_client):
    post = PostFactory()
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.post(like_url(post.id))
    assert response.status_code == 201
    assert Like.objects.filter(user=user, post=post).exists()


def test_unverified_user_can_like(api_client):
    post = PostFactory()
    user = UserFactory(is_verified=False)
    api_client.force_authenticate(user=user)
    response = api_client.post(like_url(post.id))
    assert response.status_code == 201


def test_cannot_like_own_post(api_client):
    post = PostFactory()
    api_client.force_authenticate(user=post.author)
    response = api_client.post(like_url(post.id))
    assert response.status_code == 403
    assert Like.objects.count() == 0


def test_cannot_like_twice(api_client):
    post = PostFactory()
    user = UserFactory()
    api_client.force_authenticate(user=user)
    api_client.post(like_url(post.id))
    response = api_client.post(like_url(post.id))
    assert response.status_code == 400
    assert Like.objects.count() == 1


def test_like_requires_auth(api_client):
    post = PostFactory()
    response = api_client.post(like_url(post.id))
    assert response.status_code == 401


def test_like_missing_post(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.post(like_url("00000000-0000-0000-0000-000000000000"))
    assert response.status_code == 404


def test_unlike(api_client):
    post = PostFactory()
    user = UserFactory()
    api_client.force_authenticate(user=user)
    api_client.post(like_url(post.id))
    response = api_client.delete(like_url(post.id))
    assert response.status_code == 204
    assert Like.objects.count() == 0


def test_unlike_without_like_returns_404(api_client):
    post = PostFactory()
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.delete(like_url(post.id))
    assert response.status_code == 404


def test_db_unique_constraint(api_client):
    post = PostFactory()
    user = UserFactory()
    Like.objects.create(user=user, post=post)
    with pytest.raises(IntegrityError):
        Like.objects.create(user=user, post=post)
