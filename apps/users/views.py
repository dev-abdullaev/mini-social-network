from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import generics, status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView

from apps.core.serializers import (
    RESP_400,
    RESP_401,
    RESP_404,
    RESP_429,
    DetailSerializer,
    TokenPairSerializer,
)

from . import lockout
from .models import EmailVerificationToken, Follow, PasswordResetToken, User
from .serializers import (
    FollowUserSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from .tasks import send_password_reset_email, send_verification_email


@extend_schema(
    tags=["auth"],
    summary="Register a new user",
    description=(
        "Create a new user account. The account is created unverified; a verification "
        "email is sent immediately, and the user must call the verify-email endpoint "
        "before they can use verification-gated features."
    ),
    responses={
        201: UserSerializer,
        400: RESP_400,
        429: RESP_429,
    },
    examples=[
        OpenApiExample(
            "Register",
            value={
                "email": "jane@example.com",
                "username": "jane_doe",
                "full_name": "Jane Doe",
                "password": "correct-horse-battery",
            },
            request_only=True,
        ),
    ],
)
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        tags=["auth"],
        summary="Log in",
        description=(
            "Authenticate with either an email or a username plus a password, and receive "
            "a JWT access/refresh token pair. Use the access token as "
            "`Authorization: Bearer <access>` on subsequent requests. After too many failed "
            "attempts for the same identifier in a short window, the identifier is "
            "temporarily locked out and login returns 429 regardless of credentials."
        ),
        request=LoginSerializer,
        responses={
            200: TokenPairSerializer,
            400: RESP_400,
            401: RESP_401,
            429: RESP_429,
        },
        examples=[
            OpenApiExample(
                "Login with email",
                value={"email": "jane@example.com", "password": "correct-horse-battery"},
                request_only=True,
            ),
            OpenApiExample(
                "Login with username",
                value={"username": "jane_doe", "password": "correct-horse-battery"},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        identifier = data.get("email") or data.get("username")
        if lockout.is_locked(identifier):
            return Response(
                {"detail": "Too many failed attempts. Try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if data.get("email"):
            user = User.objects.filter(email__iexact=data["email"]).first()
        else:
            user = User.objects.filter(username__iexact=data["username"]).first()
        if user is None or not user.is_active or not user.check_password(data["password"]):
            lockout.register_failure(identifier)
            raise AuthenticationFailed("Invalid credentials.")
        lockout.reset(identifier)
        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})


@extend_schema(
    tags=["auth"],
    summary="Refresh access token",
    description=(
        "Exchange a valid refresh token for a new access token. Refresh token rotation is "
        "enabled, so a new refresh token is also returned and the old one is blacklisted."
    ),
    responses={
        200: TokenPairSerializer,
        401: RESP_401,
    },
)
class TokenRefreshView(SimpleJWTTokenRefreshView):
    """Thin wrapper around simplejwt's TokenRefreshView solely to attach OpenAPI metadata."""


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        summary="Log out",
        description=(
            "Blacklist the given refresh token, invalidating it for future use. Requires a "
            "valid access token in the Authorization header."
        ),
        request=LogoutSerializer,
        responses={
            205: None,
            400: DetailSerializer,
            401: DetailSerializer,
        },
    )
    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(status=status.HTTP_205_RESET_CONTENT)


@extend_schema(
    tags=["users"],
    summary="Get the current user",
    description="Return the profile of the authenticated user.",
    responses={
        200: UserSerializer,
        401: RESP_401,
    },
)
class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


@extend_schema(
    tags=["users"],
    summary="Update the current user's profile",
    description="Partially update the authenticated user's profile (username, full name, avatar).",
    responses={
        200: UserUpdateSerializer,
        400: RESP_400,
        401: RESP_401,
    },
)
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


class FollowView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["follows"],
        summary="Follow a user",
        description="Start following the given user. A user cannot follow themselves.",
        request=None,
        responses={
            201: DetailSerializer,
            400: DetailSerializer,
            404: DetailSerializer,
            401: DetailSerializer,
        },
    )
    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        if target.id == request.user.id:
            return Response(
                {"detail": "You cannot follow yourself."}, status=status.HTTP_400_BAD_REQUEST
            )
        _, created = Follow.objects.get_or_create(follower=request.user, following=target)
        if not created:
            return Response({"detail": "Already following."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Followed."}, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["follows"],
        summary="Unfollow a user",
        description="Stop following the given user.",
        responses={
            204: None,
            404: DetailSerializer,
            401: DetailSerializer,
        },
    )
    def delete(self, request, user_id):
        deleted, _ = Follow.objects.filter(follower=request.user, following_id=user_id).delete()
        if not deleted:
            return Response({"detail": "Not following."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["users"],
    summary="List a user's followers",
    description="Return the users who follow the given user, ordered by username.",
    responses={
        200: FollowUserSerializer,
        404: RESP_404,
    },
)
class FollowersListView(generics.ListAPIView):
    serializer_class = FollowUserSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        get_object_or_404(User, pk=self.kwargs["user_id"])
        return User.objects.filter(following__following_id=self.kwargs["user_id"]).order_by(
            "username"
        )


@extend_schema(
    tags=["users"],
    summary="List who a user is following",
    description="Return the users that the given user follows, ordered by username.",
    responses={
        200: FollowUserSerializer,
        404: RESP_404,
    },
)
class FollowingListView(generics.ListAPIView):
    serializer_class = FollowUserSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        get_object_or_404(User, pk=self.kwargs["user_id"])
        return User.objects.filter(followers__follower_id=self.kwargs["user_id"]).order_by(
            "username"
        )


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["auth"],
        summary="Verify email address",
        description="Consume a one-time email verification token and mark the account as verified.",
        parameters=[OpenApiParameter(name="token", type=str, required=True)],
        responses={200: DetailSerializer, 400: DetailSerializer},
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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    @extend_schema(
        tags=["auth"],
        summary="Resend verification email",
        description=(
            "Send a new email verification token to the authenticated user, if not already "
            "verified."
        ),
        request=None,
        responses={
            200: DetailSerializer,
            400: RESP_400,
            401: RESP_401,
            429: RESP_429,
        },
    )
    def post(self, request):
        if request.user.is_verified:
            return Response(
                {"detail": "Email is already verified."}, status=status.HTTP_400_BAD_REQUEST
            )
        token = EmailVerificationToken.issue(request.user)
        send_verification_email.delay(str(request.user.id), token.token)
        return Response({"detail": "Verification email sent."})


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    @extend_schema(
        tags=["auth"],
        summary="Request a password reset",
        description=(
            "Send a password reset link to the given email if an active account exists for "
            "it. Always returns 200 regardless of whether the email is registered, to avoid "
            "leaking account existence."
        ),
        request=PasswordResetRequestSerializer,
        responses={
            200: DetailSerializer,
            400: RESP_400,
            429: RESP_429,
        },
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        # Do NOT reveal whether the email exists (anti-enumeration): always 200.
        if user is not None and user.is_active:
            token = PasswordResetToken.issue(user)
            send_password_reset_email.delay(str(user.id), token.token)
        return Response({"detail": "If that email exists, a reset link has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        tags=["auth"],
        summary="Confirm a password reset",
        description=(
            "Set a new password using a valid password reset token. On success, all "
            "outstanding JWT tokens for the user are blacklisted, so previously issued "
            "sessions must log in again."
        ),
        request=PasswordResetConfirmSerializer,
        responses={
            200: DetailSerializer,
            400: OpenApiResponse(
                DetailSerializer,
                description=(
                    "Validation error. Either a field-keyed body for an invalid/weak "
                    'new_password, e.g. {"new_password": ["..."]}, or a plain '
                    '{"detail": "Invalid or expired token."} if the reset token is '
                    "missing, already used, or expired."
                ),
            ),
            429: OpenApiResponse(
                DetailSerializer,
                description=(
                    'Rate limit exceeded. This endpoint shares the "login" throttle '
                    "scope with the login endpoint."
                ),
            ),
        },
        examples=[
            OpenApiExample(
                "Confirm reset",
                value={"token": "a1b2c3d4e5f6", "new_password": "correct-horse-battery"},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            token = (
                PasswordResetToken.objects.select_for_update()
                .select_related("user")
                .filter(token=serializer.validated_data["token"])
                .first()
            )
            if token is None or not token.is_valid or not token.user.is_active:
                return Response(
                    {"detail": "Invalid or expired token."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            token.used_at = timezone.now()
            token.save(update_fields=["used_at"])
            user = token.user
            user.set_password(serializer.validated_data["new_password"])
            user.save(update_fields=["password", "updated_at"])
            for outstanding in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding)
            PasswordResetToken.objects.filter(user=user, used_at__isnull=True).exclude(
                pk=token.pk
            ).update(used_at=timezone.now())
        return Response({"detail": "Password has been reset."})
