import pytest
from django.core.management import call_command

from apps.posts.models import Comment, Like, Post
from apps.users.models import Follow, User

pytestmark = pytest.mark.django_db


def test_seed_demo_creates_data():
    call_command("seed_demo")
    assert User.objects.filter(email__endswith="@demo.local").count() == 5
    assert Post.objects.count() == 10
    # comments/likes/follows are randomized but deterministic (seeded rng),
    # so at least some of each must exist.
    assert Comment.objects.exists()
    assert Like.objects.exists()
    assert Follow.objects.exists()


def test_seed_demo_flush_is_idempotent():
    call_command("seed_demo")
    call_command("seed_demo", "--flush")
    # after a flush + reseed the demo user count stays at 5 (no duplicates)
    assert User.objects.filter(email__endswith="@demo.local").count() == 5
    assert Post.objects.count() == 10


def test_seeded_users_can_authenticate():
    call_command("seed_demo")
    user = User.objects.get(username="kamran")
    assert user.is_verified is True
    assert user.check_password("demopass123")
