from contextlib import contextmanager

from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import user_has_role

from . import services
from .filters import AdminProfileFilter, AlumniRegistrationFilter, PublicDirectoryFilter
from .imports import ImportFormatError, import_alumni, parse_csv
from .models import AlumniImport, AlumniProfile, AlumniRegistration
from .permissions import (
    CanImportAlumni,
    CanManageDirectory,
    CanReadAdminDirectory,
    CanReviewRegistrations,
)
from .serializers import (
    DOUBLON_MESSAGE,
    AdminProfileSerializer,
    AlumniImportCreateSerializer,
    AlumniImportSerializer,
    AlumniRegistrationAdminSerializer,
    AlumniRegistrationCreateSerializer,
    InvitationActivateSerializer,
    InvitationVerifySerializer,
    MemberDirectorySerializer,
    PublicDirectorySerializer,
    RejectSerializer,
    SelfProfileSerializer,
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


@contextmanager
def _already_reviewed_as_400():
    """Traduit en `ValidationError` DRF (400) le refus qui fait foi côté
    service (`RegistrationAlreadyReviewed`, posé sous verrou). Même forme que
    `_invitation_errors_as_400()` ci-dessus : point de traduction unique pour
    les deux actions, plutôt qu'un `try/except` dupliqué dans chacune.
    """
    try:
        yield
    except services.RegistrationAlreadyReviewed as exc:
        raise ValidationError({"statut": [str(exc)]}) from exc


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
        """Chemin rapide et amical : évite un aller-retour service + verrou
        quand le statut est visiblement déjà tranché. Ce n'est qu'un confort
        — la garantie d'unicité de l'instruction est posée par le service
        sous `select_for_update()` (voir `services.approve_registration`),
        pas ici : la correction ne dépend pas de cet appel préalable.
        """
        registration = self.get_object()
        if registration.status != AlumniRegistration.Status.EN_ATTENTE:
            raise ValidationError(
                {"statut": [services.REGISTRATION_ALREADY_REVIEWED_MESSAGE]}
            )
        return registration

    @extend_schema(request=None, responses={200: AdminProfileSerializer})
    @action(detail=True, methods=["post"], url_path="approuver")
    def approuver(self, request, pk=None):
        registration = self._en_attente_ou_400()
        with _already_reviewed_as_400():
            profile = services.approve_registration(
                registration, reviewer=request.user
            )
        return Response(AdminProfileSerializer(profile).data)

    @extend_schema(
        request=RejectSerializer, responses={200: AlumniRegistrationAdminSerializer}
    )
    @action(detail=True, methods=["post"], url_path="rejeter")
    def rejeter(self, request, pk=None):
        registration = self._en_attente_ou_400()
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with _already_reviewed_as_400():
            services.reject_registration(
                registration,
                reviewer=request.user,
                reason=serializer.validated_data["motif"],
            )
        registration.refresh_from_db()
        return Response(self.get_serializer(registration).data)


# Rôles qui accèdent au niveau « connecté » de l'annuaire.
DIRECTORY_ROLES = ("Alumni", "Secrétaire", "Administrateur")


@extend_schema(tags=["alumni"])
class DirectoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Annuaire des alumni.

    Un seul URL, deux niveaux de champs : le sérialiseur est choisi selon le
    rôle de l'appelant. La *présence* dans l'annuaire est portée par
    `in_directory()` — statut actif et consentement — quel que soit le niveau.
    """

    permission_classes = [AllowAny]
    filterset_class = PublicDirectoryFilter
    search_fields = [
        "first_name",
        "last_name",
        "organization",
        "current_position",
    ]
    ordering_fields = ["last_name", "promotion"]
    ordering = ["last_name", "first_name"]

    def get_queryset(self):
        return AlumniProfile.objects.in_directory()

    def get_serializer_class(self):
        user = self.request.user
        if user.is_authenticated and (
            user.is_superuser
            or any(user_has_role(user, role) for role in DIRECTORY_ROLES)
        ):
            return MemberDirectorySerializer
        return PublicDirectorySerializer


@extend_schema(tags=["alumni"])
class AdminProfileViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Base alumni complète : tous les statuts, e-mails inclus.

    Lecture ouverte à la Secrétaire ; modification et actes de gouvernance
    réservés à l'Administrateur.
    """

    queryset = AlumniProfile.objects.select_related("user", "mandate")
    serializer_class = AdminProfileSerializer
    permission_classes = [CanReadAdminDirectory]
    filterset_class = AdminProfileFilter
    search_fields = [
        "email",
        "first_name",
        "last_name",
        "organization",
        "current_position",
    ]
    ordering_fields = ["last_name", "promotion", "created_at"]
    http_method_names = ["get", "patch", "post", "head", "options"]

    ACTIONS_RESERVEES = (
        "partial_update",
        "suspendre",
        "reactiver",
        "archiver",
        "inviter",
    )

    def get_permissions(self):
        if self.action in self.ACTIONS_RESERVEES:
            return [CanManageDirectory()]
        return super().get_permissions()

    def _repondre(self, profile):
        return Response(self.get_serializer(profile).data)

    @extend_schema(request=None, responses={200: AdminProfileSerializer})
    @action(detail=True, methods=["post"], url_path="suspendre")
    def suspendre(self, request, pk=None):
        return self._repondre(services.suspend_profile(self.get_object()))

    @extend_schema(request=None, responses={200: AdminProfileSerializer})
    @action(detail=True, methods=["post"], url_path="reactiver")
    def reactiver(self, request, pk=None):
        return self._repondre(services.reactivate_profile(self.get_object()))

    @extend_schema(request=None, responses={200: AdminProfileSerializer})
    @action(detail=True, methods=["post"], url_path="archiver")
    def archiver(self, request, pk=None):
        return self._repondre(services.archive_profile(self.get_object()))

    @extend_schema(request=None, responses={200: AdminProfileSerializer})
    @action(detail=True, methods=["post"], url_path="inviter")
    def inviter(self, request, pk=None):
        profile = self.get_object()
        if profile.user_id is not None:
            raise ValidationError(
                {"compte": ["Ce profil possède déjà un compte de connexion."]}
            )
        services.send_invitation(profile)
        return self._repondre(profile)


@extend_schema(tags=["alumni"])
class SelfProfileView(generics.RetrieveUpdateAPIView):
    """Profil du titulaire du compte.

    Aucune permission de niveau objet : le périmètre est porté par le
    queryset (`user=request.user`), donc aucun chemin de code ne permet
    d'atteindre le profil d'un autre alumni.
    """

    serializer_class = SelfProfileSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        profile = AlumniProfile.objects.filter(user=self.request.user).first()
        if profile is None:
            raise NotFound("Aucun profil alumni n'est rattaché à ce compte.")
        return profile


@extend_schema(tags=["alumni"])
class AdminImportViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Dépôt d'un fichier d'alumni et consultation des rapports."""

    queryset = AlumniImport.objects.select_related("uploaded_by").prefetch_related(
        "errors"
    )
    serializer_class = AlumniImportSerializer
    permission_classes = [CanImportAlumni]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request=AlumniImportCreateSerializer, responses={201: AlumniImportSerializer}
    )
    def create(self, request):
        serializer = AlumniImportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fichier = serializer.validated_data["fichier"]

        try:
            lignes = parse_csv(fichier)
        except (ImportFormatError, UnicodeDecodeError) as exc:
            raise ValidationError({"fichier": [str(exc)]}) from exc

        rapport = import_alumni(
            lignes,
            uploaded_by=request.user,
            strict=serializer.validated_data["strict"],
            filename=fichier.name,
        )
        return Response(
            AlumniImportSerializer(rapport).data, status=status.HTTP_201_CREATED
        )
