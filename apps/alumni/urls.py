from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminProfileViewSet,
    AdminRegistrationViewSet,
    DirectoryViewSet,
    InvitationActivateView,
    InvitationVerifyView,
    RegistrationCreateView,
)

router = DefaultRouter()
router.register("annuaire", DirectoryViewSet, basename="alumni-annuaire")
router.register(
    "admin/inscriptions", AdminRegistrationViewSet, basename="alumni-admin-inscription"
)
router.register("admin/profils", AdminProfileViewSet, basename="alumni-admin-profil")

urlpatterns = [
    path(
        "inscriptions/",
        RegistrationCreateView.as_view(),
        name="alumni-inscription-create",
    ),
    path(
        "invitation/verifier/",
        InvitationVerifyView.as_view(),
        name="alumni-invitation-verify",
    ),
    path(
        "invitation/activer/",
        InvitationActivateView.as_view(),
        name="alumni-invitation-activate",
    ),
    path("", include(router.urls)),
]
