from django.conf import settings
from django.contrib.auth import authenticate
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.tokens import RefreshToken as RefreshTokenType

from .cookies import clear_auth_cookies, set_auth_cookies
from .serializers import LoginSerializer, UserSerializer


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Identifiants invalides."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        refresh = RefreshToken.for_user(user)
        response = Response(UserSerializer(user).data)
        set_auth_cookies(response, refresh.access_token, refresh)
        get_token(request)  # force la pose du cookie CSRF
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if not raw:
            return Response(
                {"detail": "Refresh token manquant."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            refresh = RefreshTokenType(raw)
        except TokenError:
            return Response(
                {"detail": "Refresh token invalide."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        access = refresh.access_token
        response = Response({"detail": "Token rafraîchi."})
        # Rotation : on blackliste l'ancien refresh et on en repose un neuf
        if settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS"):
            try:
                refresh.blacklist()
            except AttributeError:
                pass
            user_id = refresh.get("user_id")
            new_refresh = RefreshTokenType()
            new_refresh["user_id"] = user_id
            set_auth_cookies(response, access, new_refresh)
        else:
            set_auth_cookies(response, access, refresh)
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if raw:
            try:
                RefreshTokenType(raw).blacklist()
            except (TokenError, AttributeError):
                pass
        response = Response({"detail": "Déconnecté."})
        clear_auth_cookies(response)
        return response
