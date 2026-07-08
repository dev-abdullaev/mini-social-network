"""Lightweight, response-only serializers shared across apps.

These exist purely to document response shapes for drf-spectacular; they are
never used to validate incoming data.
"""

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
