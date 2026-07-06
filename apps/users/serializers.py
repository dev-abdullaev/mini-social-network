from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import User

USERNAME_VALIDATOR = RegexValidator(
    regex=r"^[A-Za-z0-9_]+$",
    message="Username may contain only latin letters, digits and underscores.",
)
FULL_NAME_VALIDATOR = RegexValidator(
    regex=r"^[A-Za-zА-Яа-яЁё\s-]+$",
    message="Full name may contain only letters, spaces and hyphens.",
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "full_name", "is_verified", "created_at"]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        min_length=3,
        max_length=32,
        validators=[USERNAME_VALIDATOR, UniqueValidator(queryset=User.objects.all())],
    )
    full_name = serializers.CharField(
        min_length=2, max_length=100, validators=[FULL_NAME_VALIDATOR]
    )
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["email", "username", "full_name", "password"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
