import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models.functions import Upper
from django.utils import timezone

from apps.core.models import CreatedAtModel, TimeStampedModel, UUIDModel

from .managers import UserManager


class User(UUIDModel, TimeStampedModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=32, unique=True)
    full_name = models.CharField(max_length=100)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "full_name"]

    class Meta:
        indexes = [
            models.Index(Upper("email"), name="user_email_ci_idx"),
            models.Index(Upper("username"), name="user_username_ci_idx"),
        ]

    def __str__(self):
        return self.username


class EmailVerificationToken(UUIDModel, CreatedAtModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="verification_tokens"
    )
    token = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, user):
        return cls.objects.create(
            user=user,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(hours=settings.VERIFICATION_TOKEN_TTL_HOURS),
        )

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()


class Follow(UUIDModel, CreatedAtModel):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="following"
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="followers"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["follower", "following"], name="unique_follow"),
            models.CheckConstraint(
                condition=~models.Q(follower=models.F("following")), name="no_self_follow"
            ),
        ]


class PasswordResetToken(UUIDModel, CreatedAtModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_tokens"
    )
    token = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, user):
        return cls.objects.create(
            user=user,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(hours=settings.PASSWORD_RESET_TOKEN_TTL_HOURS),
        )

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()
