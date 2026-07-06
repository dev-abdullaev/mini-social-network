from rest_framework import generics, status
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
        user = serializer.save()
        token = EmailVerificationToken.issue(user)
        send_verification_email.delay(str(user.id), token.token)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
