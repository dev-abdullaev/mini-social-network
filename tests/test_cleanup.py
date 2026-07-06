from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.posts.models import Post
from apps.posts.tasks import cleanup_old_posts
from apps.users.models import User
from apps.users.tasks import cleanup_unverified_users
from tests.factories import PostFactory, UserFactory

pytestmark = pytest.mark.django_db


def backdate_user(user, hours):
    User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(hours=hours))


def test_cleanup_deletes_stale_unverified():
    stale = UserFactory(is_verified=False)
    backdate_user(stale, hours=48)
    deleted = cleanup_unverified_users()
    assert deleted == 1
    assert not User.objects.filter(pk=stale.pk).exists()


def test_cleanup_keeps_fresh_unverified():
    UserFactory(is_verified=False)
    assert cleanup_unverified_users() == 0
    assert User.objects.count() == 1


def test_cleanup_keeps_verified():
    old_verified = UserFactory(is_verified=True)
    backdate_user(old_verified, hours=48)
    assert cleanup_unverified_users() == 0


def test_cleanup_keeps_staff():
    staff = UserFactory(is_verified=False, is_staff=True)
    backdate_user(staff, hours=48)
    assert cleanup_unverified_users() == 0


def test_cleanup_management_command():
    stale = UserFactory(is_verified=False)
    backdate_user(stale, hours=48)
    call_command("cleanup_unverified_users")
    assert not User.objects.filter(pk=stale.pk).exists()


def test_cleanup_old_posts_disabled_by_default(settings):
    settings.POST_TTL_DAYS = 0
    post = PostFactory()
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(days=365))
    assert cleanup_old_posts() == 0
    assert Post.objects.count() == 1


def test_cleanup_old_posts_when_enabled(settings):
    settings.POST_TTL_DAYS = 30
    old = PostFactory()
    Post.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))
    PostFactory()  # fresh
    assert cleanup_old_posts() == 1
    assert Post.objects.count() == 1
