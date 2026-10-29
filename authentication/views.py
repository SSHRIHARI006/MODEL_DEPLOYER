from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.throttling import ConfigurableScopedRateThrottle

from .serializers import RegisterSerializer


class RegisterAPIView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [ConfigurableScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "User created successfully",
                "username": user.username,
                "email": user.email,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginAPIView(TokenObtainPairView):
    """SEC-07: SimpleJWT disables throttling on its own views; re-enable it."""

    throttle_classes = [ConfigurableScopedRateThrottle]
    throttle_scope = "auth"


class RefreshAPIView(TokenRefreshView):
    """SEC-07: refresh rotates and revokes the presented token."""

    throttle_classes = [ConfigurableScopedRateThrottle]
    throttle_scope = "auth"


class LogoutAPIView(APIView):
    """Revoke a refresh token so it can never be exchanged again (SEC-07).

    Unauthenticated on purpose: possession of the refresh token is the proof,
    and clients must be able to log out even after their access token expired.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ConfigurableScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        raw_refresh = request.data.get("refresh")
        if not raw_refresh:
            return Response(
                {"error": "refresh token is required", "code": "REFRESH_REQUIRED"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            RefreshToken(raw_refresh).blacklist()
        except TokenError:
            return Response(
                {
                    "error": "refresh token is invalid, expired, or already revoked",
                    "code": "INVALID_REFRESH",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"message": "Session revoked"})
