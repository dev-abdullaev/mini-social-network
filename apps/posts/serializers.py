from rest_framework import serializers

from apps.users.models import User

from .models import Post


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username"]


class PostSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    title = serializers.CharField(min_length=5, max_length=255)
    content = serializers.CharField(max_length=10000)

    class Meta:
        model = Post
        fields = ["id", "author", "title", "content", "created_at", "updated_at"]
        read_only_fields = ["id", "author", "created_at", "updated_at"]
