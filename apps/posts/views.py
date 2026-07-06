from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly

from apps.core.permissions import IsOwnerOrReadOnly, IsVerified

from .filters import PostFilter
from .models import Comment, Post
from .serializers import (
    CommentSerializer,
    PostDetailSerializer,
    PostSerializer,
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
            qs = qs.prefetch_related("comments__author")
        return qs

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


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


class CommentDeleteView(generics.DestroyAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    lookup_url_kwarg = "comment_id"

    def get_queryset(self):
        return Comment.objects.filter(post_id=self.kwargs["post_id"])
