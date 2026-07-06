from django.db import IntegrityError, transaction
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import EmailVerificationToken
from .serializers import RegisterSerializer, UserSerializer
from .tasks import send_verification_email


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = serializer.save()
                token = EmailVerificationToken.issue(user)
        except IntegrityError as exc:
            raise ValidationError(
                {"detail": "User with this email or username already exists."}
            ) from exc
        send_verification_email.delay(str(user.id), token.token)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
