import io

import pytest
from PIL import Image

from apps.posts.models import Post
from tests.factories import PostFactory, UserFactory

pytestmark = pytest.mark.django_db

USERS_ME_URL = "/api/users/me/"
AUTH_ME_URL = "/api/auth/me/"
POSTS_URL = "/api/posts/"


def _png(name="a.png"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    buf = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


def _not_an_image(name="a.png"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, b"not a real image", content_type="image/png")


def _post_detail_url(post_id):
    return f"{POSTS_URL}{post_id}/"


def test_patch_user_avatar(api_client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    user = UserFactory()
    api_client.force_authenticate(user=user)

    response = api_client.patch(USERS_ME_URL, {"avatar": _png()}, format="multipart")

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.avatar

    me_response = api_client.get(AUTH_ME_URL)
    assert me_response.status_code == 200
    assert me_response.json()["avatar"]


def test_create_post_with_image(api_client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)

    response = api_client.post(
        POSTS_URL,
        {"title": "Hello world", "content": "text", "image": _png()},
        format="multipart",
    )

    assert response.status_code == 201
    post = Post.objects.get()
    assert post.image

    detail_response = api_client.get(_post_detail_url(post.id))
    assert detail_response.status_code == 200
    assert detail_response.json()["image"]


def test_create_post_without_image(api_client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    user = UserFactory(is_verified=True)
    api_client.force_authenticate(user=user)

    response = api_client.post(
        POSTS_URL,
        {"title": "Hello world", "content": "text"},
        format="multipart",
    )

    assert response.status_code == 201
    post = Post.objects.get()
    assert not post.image
    assert response.json()["image"] is None


def test_patch_avatar_rejects_non_image(api_client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    user = UserFactory()
    api_client.force_authenticate(user=user)

    response = api_client.patch(USERS_ME_URL, {"avatar": _not_an_image()}, format="multipart")

    assert response.status_code == 400
    assert "avatar" in response.json()


def test_patch_own_post_with_image(api_client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    post = PostFactory()
    api_client.force_authenticate(user=post.author)

    response = api_client.patch(_post_detail_url(post.id), {"image": _png()}, format="multipart")

    assert response.status_code == 200
    post.refresh_from_db()
    assert post.image
