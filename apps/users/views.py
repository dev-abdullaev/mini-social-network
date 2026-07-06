from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import EmailVerificationToken, User
from .serializers import LoginSerializer, RegisterSerializer, UserSerializer, UserUpdateSerializer
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


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("email"):
            user = User.objects.filter(email__iexact=data["email"]).first()
        else:
            user = User.objects.filter(username__iexact=data["username"]).first()
        if user is None or not user.is_active or not user.check_password(data["password"]):
            raise AuthenticationFailed("Invalid credentials.")
        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserMeView(generics.UpdateAPIView):
    serializer_class = UserUpdateSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["patch"]

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            raise ValidationError({"username": ["This username is already taken."]}) from exc


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[OpenApiParameter(name="token", type=str, required=True)],
        responses={200: None, 400: None},
    )
    def get(self, request):
        token_value = request.query_params.get("token", "")
        with transaction.atomic():
            token = (
                EmailVerificationToken.objects.select_for_update()
                .select_related("user")
                .filter(token=token_value)
                .first()
            )
            if token is None or not token.is_valid:
                return Response(
                    {"detail": "Invalid or expired token."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            token.used_at = timezone.now()
            token.save(update_fields=["used_at"])
            user = token.user
            if not user.is_verified:
                user.is_verified = True
                user.save(update_fields=["is_verified", "updated_at"])
        return Response({"detail": "Email verified."})


class ResendVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.is_verified:
            return Response(
                {"detail": "Email is already verified."}, status=status.HTTP_400_BAD_REQUEST
            )
        token = EmailVerificationToken.issue(request.user)
        send_verification_email.delay(str(request.user.id), token.token)
        return Response({"detail": "Verification email sent."})
