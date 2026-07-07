from django.contrib import admin

from .models import EmailVerificationToken, Follow, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "username", "full_name", "is_verified", "is_staff", "created_at")
    list_filter = ("is_verified", "is_staff", "is_active", "created_at")
    search_fields = ("email", "username", "full_name")
    ordering = ("-created_at",)
    readonly_fields = ("id", "password", "created_at", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("id", "email", "username", "full_name", "password")}),
        ("Status", {"fields": ("is_verified", "is_active", "is_staff", "is_superuser")}),
        ("Permissions", {"fields": ("groups", "user_permissions")}),
        ("Timestamps", {"fields": ("last_login", "created_at", "updated_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        # Only superusers may grant staff/superuser status or permissions,
        # so a non-superuser staff member can't escalate their own privileges.
        if not request.user.is_superuser:
            readonly += ["is_staff", "is_superuser", "groups", "user_permissions"]
        return readonly


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "expires_at", "used_at", "created_at")
    list_filter = ("used_at", "expires_at")
    search_fields = ("user__email", "user__username")
    ordering = ("-created_at",)
    readonly_fields = ("id", "user", "token", "created_at", "expires_at", "used_at")


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "following", "created_at")
    search_fields = ("follower__username", "following__username")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at")
    autocomplete_fields = ("follower", "following")
