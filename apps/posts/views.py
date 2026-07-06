from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from apps.core.permissions import IsOwnerOrReadOnly, IsVerified

from .filters import PostFilter
from .models import Post
from .serializers import PostSerializer


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsVerified, IsOwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = PostFilter
    search_fields = ["title", "content"]

    def get_queryset(self):
        return Post.objects.select_related("author").order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
