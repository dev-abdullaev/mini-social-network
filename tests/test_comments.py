import pytest

from apps.posts.models import Comment
from tests.factories import CommentFactory, PostFactory, UserFactory

pytestmark = pytest.mark.django_db


def comments_url(post_id):
    return f"/api/posts/{post_id}/comments/"


def comment_url(post_id, comment_id):
    return f"/api/posts/{post_id}/comments/{comment_id}/"


def test_list_comments(api_client):
    comment = CommentFactory()
    CommentFactory(post=comment.post)
    response = api_client.get(comments_url(comment.post_id))
    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_create_comment_verified(api_client):
    post = PostFactory()
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(comments_url(post.id), {"content": "Nice post!"})
    assert response.status_code == 201
    comment = Comment.objects.get()
    assert comment.author == user
    assert comment.post == post


def test_create_comment_unverified_forbidden(api_client):
    post = PostFactory()
    user = UserFactory(is_verified=False)
    api_client.force_authenticate(user=user)
    response = api_client.post(comments_url(post.id), {"content": "Nope"})
    assert response.status_code == 403


def test_create_comment_missing_post(api_client):
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(
        comments_url("00000000-0000-0000-0000-000000000000"), {"content": "Hi"}
    )
    assert response.status_code == 404


def test_create_comment_too_long(api_client):
    post = PostFactory()
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)
    response = api_client.post(comments_url(post.id), {"content": "x" * 2001})
    assert response.status_code == 400


def test_delete_own_comment(api_client):
    comment = CommentFactory()
    api_client.force_authenticate(user=comment.author)
    response = api_client.delete(comment_url(comment.post_id, comment.id))
    assert response.status_code == 204
    assert Comment.objects.count() == 0


def test_delete_foreign_comment_forbidden(api_client):
    comment = CommentFactory()
    other = UserFactory(is_verified=True)
    api_client.force_authenticate(user=other)
    response = api_client.delete(comment_url(comment.post_id, comment.id))
    assert response.status_code == 403


def test_post_detail_includes_comments(api_client):
    comment = CommentFactory(content="First!")
    response = api_client.get(f"/api/posts/{comment.post_id}/")
    assert response.status_code == 200
    body = response.json()
    assert len(body["comments"]) == 1
    assert body["comments"][0]["content"] == "First!"
