import pytest
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.authentication import CookieJWTAuthentication

User = get_user_model()


@pytest.mark.django_db
def test_cookie_auth_sans_cookie_retourne_none():
    factory = APIRequestFactory()
    request = factory.get("/api/v1/auth/me/")
    assert CookieJWTAuthentication().authenticate(request) is None


@pytest.mark.django_db
def test_cookie_auth_avec_access_valide_authentifie_sur_get():
    user = User.objects.create_user(email="a@bamfa.org", password="x")
    access = str(RefreshToken.for_user(user).access_token)
    factory = APIRequestFactory()
    request = factory.get("/api/v1/auth/me/")
    request.COOKIES[settings.AUTH_COOKIE] = access
    authenticated_user, _token = CookieJWTAuthentication().authenticate(request)
    assert authenticated_user == user
