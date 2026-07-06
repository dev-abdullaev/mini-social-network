from rest_framework import serializers

from apps.users.models import User

from .models import Comment, Post


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


class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    content = serializers.CharField(max_length=2000)

    class Meta:
        model = Comment
        fields = ["id", "author", "content", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class PostDetailSerializer(PostSerializer):
    comments = CommentSerializer(many=True, read_only=True)

    class Meta(PostSerializer.Meta):
        fields = PostSerializer.Meta.fields + ["comments"]


class FeedPostSerializer(serializers.ModelSerializer):
    likes = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = ["id", "title", "content", "likes"]

    def get_likes(self, obj):
        return [str(like.user_id) for like in obj.likes.all()]


class FeedUserSerializer(serializers.ModelSerializer):
    posts = FeedPostSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ["username", "posts"]
