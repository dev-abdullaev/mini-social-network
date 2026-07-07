from datetime import timedelta

import pytest
from django.db import IntegrityError

from apps.posts.models import Post
from apps.users.models import Follow
from tests.factories import PostFactory, UserFactory

pytestmark = pytest.mark.django_db


def follow_url(user_id):
    return f"/api/users/{user_id}/follow/"


def followers_url(user_id):
    return f"/api/users/{user_id}/followers/"


def following_url(user_id):
    return f"/api/users/{user_id}/following/"


def test_follow_user(api_client):
    follower = UserFactory()
    target = UserFactory()
    api_client.force_authenticate(user=follower)
    response = api_client.post(follow_url(target.id))
    assert response.status_code == 201
    follow = Follow.objects.get(follower=follower, following=target)
    assert follow.follower_id == follower.id
    assert follow.following_id == target.id


def test_cannot_follow_self(api_client):
    user = UserFactory()
    api_client.force_authenticate(user=user)
    response = api_client.post(follow_url(user.id))
    assert response.status_code == 400
    assert not Follow.objects.exists()


def test_cannot_follow_twice(api_client):
    follower = UserFactory()
    target = UserFactory()
    api_client.force_authenticate(user=follower)
    api_client.post(follow_url(target.id))
    response = api_client.post(follow_url(target.id))
    assert response.status_code == 400
    assert Follow.objects.count() == 1


def test_follow_requires_auth(api_client):
    target = UserFactory()
    response = api_client.post(follow_url(target.id))
    assert response.status_code == 401


def test_follow_missing_user(api_client):
    follower = UserFactory()
    api_client.force_authenticate(user=follower)
    response = api_client.post(follow_url("00000000-0000-0000-0000-000000000000"))
    assert response.status_code == 404


def test_unfollow(api_client):
    follower = UserFactory()
    target = UserFactory()
    api_client.force_authenticate(user=follower)
    api_client.post(follow_url(target.id))
    response = api_client.delete(follow_url(target.id))
    assert response.status_code == 204
    assert not Follow.objects.exists()


def test_unfollow_when_not_following_returns_404(api_client):
    follower = UserFactory()
    target = UserFactory()
    api_client.force_authenticate(user=follower)
    response = api_client.delete(follow_url(target.id))
    assert response.status_code == 404


def test_db_check_constraint_no_self_follow():
    user = UserFactory()
    with pytest.raises(IntegrityError):
        Follow.objects.create(follower=user, following=user)


def test_db_unique_constraint():
    follower = UserFactory()
    target = UserFactory()
    Follow.objects.create(follower=follower, following=target)
    with pytest.raises(IntegrityError):
        Follow.objects.create(follower=follower, following=target)


def test_followers_list_returns_users_who_follow_target(api_client):
    target = UserFactory(username="target")
    follower_a = UserFactory(username="alice")
    follower_b = UserFactory(username="bob")
    other_user = UserFactory(username="carol")
    Follow.objects.create(follower=follower_a, following=target)
    Follow.objects.create(follower=follower_b, following=target)
    # other_user follows nobody, and is not followed by target either.
    Follow.objects.create(follower=other_user, following=follower_a)

    response = api_client.get(followers_url(target.id))
    assert response.status_code == 200
    usernames = {entry["username"] for entry in response.json()["results"]}
    assert usernames == {"alice", "bob"}
    assert "carol" not in usernames


def test_following_list_returns_users_target_follows(api_client):
    target = UserFactory(username="target2")
    followed_a = UserFactory(username="dave")
    followed_b = UserFactory(username="erin")
    unrelated = UserFactory(username="frank")
    Follow.objects.create(follower=target, following=followed_a)
    Follow.objects.create(follower=target, following=followed_b)
    Follow.objects.create(follower=unrelated, following=target)

    response = api_client.get(following_url(target.id))
    assert response.status_code == 200
    usernames = {entry["username"] for entry in response.json()["results"]}
    assert usernames == {"dave", "erin"}
    assert "frank" not in usernames


def test_followers_and_following_lists_are_not_swapped(api_client):
    user_a = UserFactory(username="a_user")
    user_b = UserFactory(username="b_user")
    # a_user follows b_user -> b_user's followers include a_user;
    # a_user's following includes b_user.
    Follow.objects.create(follower=user_a, following=user_b)

    b_followers = {
        entry["username"] for entry in api_client.get(followers_url(user_b.id)).json()["results"]
    }
    b_following = {
        entry["username"] for entry in api_client.get(following_url(user_b.id)).json()["results"]
    }
    a_followers = {
        entry["username"] for entry in api_client.get(followers_url(user_a.id)).json()["results"]
    }
    a_following = {
        entry["username"] for entry in api_client.get(following_url(user_a.id)).json()["results"]
    }

    assert b_followers == {"a_user"}
    assert b_following == set()
    assert a_followers == set()
    assert a_following == {"b_user"}


FOLLOWING_FEED_URL = "/api/feed/following/"


def test_following_feed_returns_only_followed_users_posts(api_client):
    viewer = UserFactory()
    followed_1 = UserFactory()
    followed_2 = UserFactory()
    not_followed = UserFactory()

    Follow.objects.create(follower=viewer, following=followed_1)
    Follow.objects.create(follower=viewer, following=followed_2)

    post_older = PostFactory(author=followed_1, title="Older post")
    post_newer = PostFactory(author=followed_2, title="Newer post")
    PostFactory(author=not_followed, title="Should not appear")

    # Ensure deterministic ordering regardless of factory timing.
    Post.objects.filter(pk=post_older.pk).update(
        created_at=post_newer.created_at - timedelta(minutes=5)
    )

    api_client.force_authenticate(user=viewer)
    response = api_client.get(FOLLOWING_FEED_URL)
    assert response.status_code == 200
    results = response.json()["results"]
    titles = [entry["title"] for entry in results]
    assert titles == ["Newer post", "Older post"]
    assert "Should not appear" not in titles


def test_following_feed_requires_auth(api_client):
    response = api_client.get(FOLLOWING_FEED_URL)
    assert response.status_code == 401


def test_following_feed_query_count(api_client, django_assert_max_num_queries):
    viewer = UserFactory()
    for _ in range(5):
        followed = UserFactory()
        Follow.objects.create(follower=viewer, following=followed)
        PostFactory(author=followed)

    api_client.force_authenticate(user=viewer)
    with django_assert_max_num_queries(3):
        api_client.get(FOLLOWING_FEED_URL)
