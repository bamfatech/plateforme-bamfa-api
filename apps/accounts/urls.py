from django.urls import path

from .views import CSRFTokenView, LoginView, LogoutView, MeView, RefreshView

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("csrf/", CSRFTokenView.as_view(), name="auth-csrf"),
]
