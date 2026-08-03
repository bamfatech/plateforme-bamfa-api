from django.urls import path

from .views import (
    InvitationActivateView,
    InvitationVerifyView,
    RegistrationCreateView,
)

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
]
