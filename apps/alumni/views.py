from contextlib import contextmanager

from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .filters import AlumniRegistrationFilter
from .models import AlumniRegistration
from .permissions import CanReadAdminDirectory, CanReviewRegistrations
from .serializers import (
    DOUBLON_MESSAGE,
    AdminProfileSerializer,
    AlumniRegistrationAdminSerializer,
    AlumniRegistrationCreateSerializer,
    InvitationActivateSerializer,
    InvitationVerifySerializer,
    RejectSerializer,
)


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


@contextmanager
def _invitation_errors_as_400():
    """Traduit en `ValidationError` DRF (400) toute `InvitationError` levée par
    le service — que ce soit à la résolution du jeton ou à la création du
    compte. Point unique de traduction pour les deux vues : un jeton rejoué
    en cas de double clic doit échouer proprement, qu'il soit intercepté par
    `resolve_invitation_token` (jeton déjà consommé en base) ou par
    `claim_invitation` (fenêtre de course où les deux requêtes ont franchi la
    résolution avant qu'aucune n'ait acquis le compte).
    """
    try:
        yield
    except services.InvitationError as exc:
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
        with _invitation_errors_as_400():
            profile = services.resolve_invitation_token(
                serializer.validated_data["token"]
            )
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
        with _invitation_errors_as_400():
            profile = services.resolve_invitation_token(
                serializer.validated_data["token"]
            )
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


@extend_schema(tags=["alumni"])
class AdminRegistrationViewSet(viewsets.ReadOnlyModelViewSet):
    """File d'attente des demandes d'inscription.

    Lecture ouverte à la Secrétaire, instruction réservée à l'Administrateur.
    """

    queryset = AlumniRegistration.objects.select_related("reviewed_by", "profile")
    serializer_class = AlumniRegistrationAdminSerializer
    permission_classes = [CanReadAdminDirectory]
    filterset_class = AlumniRegistrationFilter
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["submitted_at", "last_name", "promotion"]

    def get_permissions(self):
        if self.action in ("approuver", "rejeter"):
            return [CanReviewRegistrations()]
        return super().get_permissions()

    def _en_attente_ou_400(self):
        registration = self.get_object()
        if registration.status != AlumniRegistration.Status.EN_ATTENTE:
            raise ValidationError(
                {"statut": ["Cette demande a déjà été instruite."]}
            )
        return registration

    @extend_schema(request=None, responses={200: AdminProfileSerializer})
    @action(detail=True, methods=["post"], url_path="approuver")
    def approuver(self, request, pk=None):
        registration = self._en_attente_ou_400()
        profile = services.approve_registration(registration, reviewer=request.user)
        return Response(AdminProfileSerializer(profile).data)

    @extend_schema(
        request=RejectSerializer, responses={200: AlumniRegistrationAdminSerializer}
    )
    @action(detail=True, methods=["post"], url_path="rejeter")
    def rejeter(self, request, pk=None):
        registration = self._en_attente_ou_400()
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reject_registration(
            registration,
            reviewer=request.user,
            reason=serializer.validated_data["motif"],
        )
        registration.refresh_from_db()
        return Response(self.get_serializer(registration).data)
