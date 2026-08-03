from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny

from . import services
from .serializers import DOUBLON_MESSAGE, AlumniRegistrationCreateSerializer


@extend_schema(tags=["alumni"])
class RegistrationCreateView(generics.CreateAPIView):
    """Soumission publique d'une demande d'inscription alumni."""

    serializer_class = AlumniRegistrationCreateSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def perform_create(self, serializer):
        """La vérification applicative de `validate_email` ne suffit pas seule :
        deux soumissions quasi simultanées pour le même e-mail (double clic,
        retry sur timeout) peuvent toutes deux la franchir avant qu'aucune
        n'ait été enregistrée. Le dernier rempart est alors la contrainte
        d'unicité partielle en base (`unique_demande_en_attente_par_email`),
        dont l'`IntegrityError` est traduite ici dans le même message neutre,
        pour que le cas concurrent reste indiscernable du cas séquentiel.

        `serializer.save()` est fait dans un `atomic()` dédié : Postgres abandonne
        la transaction en cours dès l'échec de la contrainte, et sans ce
        savepoint explicite, toute requête suivante lèverait à son tour
        `TransactionManagementError` au lieu de laisser la connexion utilisable.
        """
        try:
            with transaction.atomic():
                registration = serializer.save()
        except IntegrityError:
            raise ValidationError({"email": [DOUBLON_MESSAGE]}) from None
        services.acknowledge_registration(registration)
