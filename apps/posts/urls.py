from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CommentDeleteView,
    CommentListCreateView,
    FeedView,
    FollowingFeedView,
    LikeView,
    PostViewSet,
)

router = DefaultRouter()
router.register("posts", PostViewSet, basename="post")

urlpatterns = [
    path("feed/following/", FollowingFeedView.as_view(), name="following-feed"),
    path("feed/", FeedView.as_view(), name="feed"),
    path(
        "posts/<uuid:post_id>/comments/",
        CommentListCreateView.as_view(),
        name="post-comments",
    ),
    path(
        "posts/<uuid:post_id>/comments/<uuid:comment_id>/",
        CommentDeleteView.as_view(),
        name="post-comment-delete",
    ),
    path("posts/<uuid:post_id>/like/", LikeView.as_view(), name="post-like"),
    *router.urls,
]
