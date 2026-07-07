from django.contrib import admin

from .models import Comment, Like, Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("title", "content", "author__username", "author__email")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("author",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("short_content", "post", "author", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content", "author__username", "post__title")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at")
    autocomplete_fields = ("post", "author")

    @admin.display(description="content")
    def short_content(self, obj):
        return obj.content[:50] + ("…" if len(obj.content) > 50 else "")


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ("user", "post", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "post__title")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at")
    autocomplete_fields = ("user", "post")
