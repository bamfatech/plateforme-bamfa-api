import pytest
from django.contrib.auth import get_user_model
from django.conf import settings
from django.conf import settings as dj_settings
from rest_framework.test import APIClient, APIRequestFactory
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


@pytest.mark.django_db
def test_login_pose_les_cookies_et_renvoie_user():
    User.objects.create_user(email="a@bamfa.org", password="motdepasse123")
    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "a@bamfa.org", "password": "motdepasse123"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["email"] == "a@bamfa.org"
    assert dj_settings.AUTH_COOKIE in response.cookies
    assert dj_settings.AUTH_COOKIE_REFRESH in response.cookies
    assert response.cookies[dj_settings.AUTH_COOKIE]["httponly"] is True


@pytest.mark.django_db
def test_login_identifiants_invalides_401():
    User.objects.create_user(email="a@bamfa.org", password="bon")
    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "a@bamfa.org", "password": "mauvais"},
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_me_sans_auth_401():
    assert APIClient().get("/api/v1/auth/me/").status_code == 401


@pytest.mark.django_db
def test_me_avec_cookie_renvoie_user():
    User.objects.create_user(email="a@bamfa.org", password="motdepasse123")
    client = APIClient()
    client.post(
        "/api/v1/auth/login/",
        {"email": "a@bamfa.org", "password": "motdepasse123"},
        format="json",
    )
    response = client.get("/api/v1/auth/me/")
    assert response.status_code == 200
    assert response.data["email"] == "a@bamfa.org"
