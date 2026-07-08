from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsOwnerOrReadOnly, IsVerified
from apps.core.serializers import DetailSerializer
from apps.users.models import User

from .filters import PostFilter
from .models import Comment, Like, Post
from .serializers import (
    CommentSerializer,
    FeedUserSerializer,
    PostDetailSerializer,
    PostSerializer,
)


@extend_schema_view(
    list=extend_schema(
        tags=["posts"],
        summary="List posts",
        description="List posts, newest first. Supports filtering and search.",
    ),
    create=extend_schema(
        tags=["posts"],
        summary="Create a post",
        description="Create a new post as the authenticated, verified user.",
    ),
    retrieve=extend_schema(
        tags=["posts"],
        summary="Get a post",
        description="Get a single post, including its recent comments and comment count.",
    ),
    update=extend_schema(
        tags=["posts"],
        summary="Replace a post",
        description="Fully replace a post. Only the post's author may update it.",
    ),
    partial_update=extend_schema(
        tags=["posts"],
        summary="Update a post",
        description="Partially update a post. Only the post's author may update it.",
    ),
    destroy=extend_schema(
        tags=["posts"],
        summary="Delete a post",
        description="Delete a post. Only the post's author may delete it.",
    ),
)
class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsVerified, IsOwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = PostFilter
    search_fields = ["title", "content"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PostDetailSerializer
        return PostSerializer

    def get_queryset(self):
        qs = Post.objects.select_related("author").order_by("-created_at")
        if self.action == "retrieve":
            qs = qs.annotate(comment_count=Count("comments"))
        return qs

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


@extend_schema_view(
    get=extend_schema(
        tags=["comments"],
        summary="List comments on a post",
        description="List comments on the given post, oldest first.",
    ),
    post=extend_schema(
        tags=["comments"],
        summary="Add a comment to a post",
        description="Create a new comment on the given post as the authenticated, verified user.",
    ),
)
class CommentListCreateView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsVerified]

    def get_queryset(self):
        get_object_or_404(Post, pk=self.kwargs["post_id"])
        return (
            Comment.objects.filter(post_id=self.kwargs["post_id"])
            .select_related("author")
            .order_by("created_at")
        )

    def perform_create(self, serializer):
        post = get_object_or_404(Post, pk=self.kwargs["post_id"])
        serializer.save(author=self.request.user, post=post)


@extend_schema(
    tags=["comments"],
    summary="Delete a comment",
    description="Delete a comment on a post. Only the comment's author may delete it.",
)
class CommentDeleteView(generics.DestroyAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    lookup_url_kwarg = "comment_id"

    def get_queryset(self):
        return Comment.objects.filter(post_id=self.kwargs["post_id"])


class LikeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["likes"],
        summary="Like a post",
        description="Like the given post. A user cannot like their own post.",
        request=None,
        responses={
            201: DetailSerializer,
            400: DetailSerializer,
            403: DetailSerializer,
            404: DetailSerializer,
            401: DetailSerializer,
        },
    )
    def post(self, request, post_id):
        post = get_object_or_404(Post, pk=post_id)
        if post.author_id == request.user.id:
            return Response(
                {"detail": "You cannot like your own post."}, status=status.HTTP_403_FORBIDDEN
            )
        _, created = Like.objects.get_or_create(user=request.user, post=post)
        if not created:
            return Response(
                {"detail": "You have already liked this post."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": "Liked."}, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["likes"],
        summary="Unlike a post",
        description="Remove the authenticated user's like from the given post.",
        responses={
            204: None,
            404: DetailSerializer,
            401: DetailSerializer,
        },
    )
    def delete(self, request, post_id):
        deleted, _ = Like.objects.filter(user=request.user, post_id=post_id).delete()
        if not deleted:
            return Response({"detail": "Like not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["feed"],
    summary="List posts from followed users",
    description="List posts authored by users the authenticated user follows, newest first.",
)
class FollowingFeedView(generics.ListAPIView):
    serializer_class = PostSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Post.objects.filter(author__followers__follower=self.request.user)
            .select_related("author")
            .order_by("-created_at")
        )


@extend_schema(
    tags=["feed"],
    summary="List the public feed",
    description="List users who have posts, each with their recent posts and like counts.",
)
class FeedView(generics.ListAPIView):
    serializer_class = FeedUserSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return (
            User.objects.filter(posts__isnull=False)
            .distinct()
            .order_by("username")
            .prefetch_related(
                Prefetch(
                    "posts",
                    queryset=Post.objects.order_by("-created_at").prefetch_related("likes"),
                )
            )
        )
