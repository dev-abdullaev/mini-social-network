from django.conf import settings
from django.db import models

from apps.core.models import CreatedAtModel, TimeStampedModel, UUIDModel


class Post(UUIDModel, TimeStampedModel):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts"
    )
    title = models.CharField(max_length=255)
    content = models.TextField(max_length=10000)
    image = models.ImageField(upload_to="post_images/", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            # Serves the follow-feed and per-author feed prefetch
            # (filter by author + order by -created_at).
            models.Index(fields=["author", "-created_at"], name="post_author_created_idx"),
        ]

    def __str__(self):
        return self.title


class Comment(UUIDModel, CreatedAtModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments"
    )
    content = models.TextField(max_length=2000)

    class Meta:
        ordering = ["created_at"]
        # Serves the per-post comment list and detail slice
        # (filter by post + order by created_at). Backward scan covers the
        # DESC latest-10 slice too, so no separate DESC index is needed.
        indexes = [models.Index(fields=["post", "created_at"], name="comment_post_created_idx")]


class Like(UUIDModel, CreatedAtModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="likes"
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "post"], name="unique_user_post_like")
        ]
