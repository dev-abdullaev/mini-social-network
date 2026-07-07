from django.urls import path

from .views import FollowersListView, FollowingListView, FollowView, UserMeView

urlpatterns = [
    path("me/", UserMeView.as_view(), name="users-me"),
    path("<uuid:user_id>/follow/", FollowView.as_view(), name="user-follow"),
    path("<uuid:user_id>/followers/", FollowersListView.as_view(), name="user-followers"),
    path("<uuid:user_id>/following/", FollowingListView.as_view(), name="user-following"),
]
