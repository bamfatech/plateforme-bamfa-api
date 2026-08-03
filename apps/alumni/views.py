from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import (
    DOUBLON_MESSAGE,
    AlumniRegistrationCreateSerializer,
    InvitationActivateSerializer,
    InvitationVerifySerializer,
)
from .services import InvitationError


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


def _resolve_or_400(token):
    try:
        return services.resolve_invitation_token(token)
    except InvitationError as exc:
        raise ValidationError({"token": [str(exc)]}) from exc


@extend_schema(
    tags=["alumni"],
    request=InvitationVerifySerializer,
    responses={200: dict},
)
class InvitationVerifyView(APIView):
    """Valide un jeton d'invitation et renvoie l'identité à préremplir."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = InvitationVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = _resolve_or_400(serializer.validated_data["token"])
        return Response({"first_name": profile.first_name, "email": profile.email})


@extend_schema(
    tags=["alumni"],
    request=InvitationActivateSerializer,
    responses={200: dict},
)
class InvitationActivateView(APIView):
    """Crée le compte de connexion à partir d'un jeton d'invitation."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = InvitationActivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = _resolve_or_400(serializer.validated_data["token"])
        _user, created = services.claim_invitation(
            profile, password=serializer.validated_data["password"]
        )
        message = (
            "Votre accès est activé. Vous pouvez maintenant vous connecter."
            if created
            else (
                "Un compte existait déjà pour cette adresse ; il a été rattaché "
                "à votre profil. Connectez-vous avec vos identifiants habituels."
            )
        )
        return Response(
            {"created": created, "detail": message}, status=status.HTTP_200_OK
        )
