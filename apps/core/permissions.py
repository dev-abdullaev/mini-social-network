from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsVerified(BasePermission):
    """Write access requires a verified email; reads are always allowed."""

    message = "Email verification required."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user.is_authenticated and request.user.is_verified)


class IsOwnerOrReadOnly(BasePermission):
    """Object writes are allowed only for the author."""

    message = "You can only modify your own content."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.author_id == request.user.id
