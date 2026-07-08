"""Lightweight, response-only serializers shared across apps.

These exist purely to document response shapes for drf-spectacular; they are
never used to validate incoming data.
"""

from drf_spectacular.utils import OpenApiResponse
from rest_framework import serializers


class TokenPairSerializer(serializers.Serializer):
    """A freshly issued JWT access/refresh token pair."""

    access = serializers.CharField(help_text="Short-lived JWT access token.")
    refresh = serializers.CharField(help_text="Long-lived JWT refresh token.")


class AccessTokenSerializer(serializers.Serializer):
    """A single refreshed JWT access token."""

    access = serializers.CharField(help_text="Newly issued JWT access token.")


class DetailSerializer(serializers.Serializer):
    """Generic message-only response used for confirmations and errors."""

    detail = serializers.CharField()


# Reusable OpenAPI 4xx response objects. Defined once here and imported by
# apps/users/views.py and apps/posts/views.py so every endpoint documents its
# error responses with consistent wording.
RESP_400 = OpenApiResponse(
    DetailSerializer,
    description=(
        'Validation error. Body is field-keyed, e.g. {"title": ["..."]}, or {"detail": "..."}.'
    ),
)
RESP_401 = OpenApiResponse(
    DetailSerializer,
    description="Authentication credentials were not provided or are invalid.",
)
RESP_403 = OpenApiResponse(
    DetailSerializer,
    description="Permission denied (email not verified, or not the owner).",
)
RESP_404 = OpenApiResponse(DetailSerializer, description="Not found.")
RESP_429 = OpenApiResponse(
    DetailSerializer,
    description="Rate limit exceeded or account temporarily locked.",
)
