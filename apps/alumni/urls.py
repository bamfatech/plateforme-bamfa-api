from django.urls import path

from .views import RegistrationCreateView

urlpatterns = [
    path(
        "inscriptions/",
        RegistrationCreateView.as_view(),
        name="alumni-inscription-create",
    ),
]
